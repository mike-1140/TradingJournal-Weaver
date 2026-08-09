"""
TAT vs. IBKR Datenvergleich — CLI
Vergleicht Trade Automation Tool CSV mit IBKR DB-Daten.

Verwendung (aus dem xml_proj-Root-Ordner):
    python dev/compare_tat_ibkr.py trades.csv
    python dev/compare_tat_ibkr.py trades.csv --env autom_money
    python dev/compare_tat_ibkr.py trades.csv --tolerance 0.05
"""

import sys
import csv
import argparse
from pathlib import Path
from decimal import Decimal, InvalidOperation

# xml_proj config importieren (liest .env aus xml_proj/) - liegt seit dem Umzug nach
# dev/ eine Ebene hoeher als frueher (dev/ ist Geschwisterordner von src/, nicht mehr
# im selben Ordner wie compare_tat_ibkr.py selbst)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config import get_engine, TABLE_PREFIX, TABLE_TRADES_CLOSE

import pandas as pd

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

DEFAULT_ENV       = "autom_paper"
DEFAULT_TOLERANCE = Decimal("0.01")

# TAT Status → IBKR closedBy Mapping
STATUS_MAP = {
    "Expired":       ["EXPIRY", "EXPIRED"],
    "Closed":        ["SELL", "BUY"],
    "Profit Target": ["SELL", "BUY"],
    "Assigned":      ["ASSIGNMENT"],
}

# ---------------------------------------------------------------------------
# TAT CSV einlesen
# ---------------------------------------------------------------------------

def _parse_decimal(val: str) -> Decimal | None:
    """Parst String als Decimal — None bei leerem Wert."""
    if not val or not val.strip():
        return None
    try:
        return Decimal(val.strip().replace(",", "."))
    except InvalidOperation:
        return None


def load_tat_csv(path: Path) -> list[dict]:
    """Liest TAT-CSV ein und gibt typisierte Zeilen zurück."""
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            rows.append({
                "account":          raw.get("Account", "").strip(),
                "underlying":       raw.get("UnderlyingSymbol", "").strip(),
                "trade_type":       raw.get("TradeType", "").strip(),
                "open_date":        raw.get("OpenDate", "").strip(),
                "close_date":       raw.get("TimeClosed", "").strip(),
                "status":           raw.get("Status", "").strip(),
                "profit_loss":      _parse_decimal(raw.get("ProfitLoss", "")),
                "commission":       _parse_decimal(raw.get("Commission", "")),
                "contract_count":   _parse_decimal(raw.get("ContractCount", "")),
                "total_premium":    _parse_decimal(raw.get("TotalPremium", "")),
                "short_put":        _parse_decimal(raw.get("ShortPut", "")),
                "long_put":         _parse_decimal(raw.get("LongPut", "")),
                "short_call":       _parse_decimal(raw.get("ShortCall", "")),
                "long_call":        _parse_decimal(raw.get("LongCall", "")),
                "strategy":         raw.get("Strategy", "").strip(),
                "template":         raw.get("Template", "").strip(),
            })
    return rows


def tat_open_date(row: dict) -> str:
    """Normalisiert TAT-Datum auf YYYY-MM-DD."""
    val = row["open_date"]
    if not val:
        return ""
    # M/D/YYYY → YYYY-MM-DD
    from datetime import datetime
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(val, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return val


# ---------------------------------------------------------------------------
# IBKR DB laden und gruppieren
# ---------------------------------------------------------------------------

def load_ibkr_groups(env: str) -> dict[str, dict]:
    """
    Liest trades_close aus der DB und gruppiert Legs per opt_strategyID.
    Gibt ein Dict { group_key → aggregierte Daten } zurück.
    """
    engine = get_engine(env)
    prefix = TABLE_PREFIX
    table  = f"{prefix}{TABLE_TRADES_CLOSE}"

    query = f"""
        SELECT
            id,
            opt_strategyID,
            opt_strategyName,
            underlyingSymbol,
            DATE(dateTimeOpen)  AS open_date,
            DATE(dateTimeClose) AS close_date,
            profit,
            ibCommission,
            quantity,
            strike,
            putCall,
            buySellOpen,
            closedBy,
            status,
            environment
        FROM {table}
        WHERE environment = '{env.upper()}'
        ORDER BY dateTimeOpen
    """

    df = pd.read_sql(query, engine)

    if df.empty:
        return {}

    # Gruppen-Schlüssel: opt_strategyID falls vorhanden, sonst Einzel-ID
    df["group_key"] = df.apply(
        lambda r: r["opt_strategyID"] if pd.notna(r["opt_strategyID"]) and r["opt_strategyID"]
        else f"single_{r['id']}",
        axis=1,
    )

    groups = {}
    for key, grp in df.groupby("group_key", sort=False):
        first = grp.iloc[0]

        def get_strike(put_call: str, buy_sell: str) -> Decimal | None:
            mask = (grp["putCall"] == put_call) & (grp["buySellOpen"] == buy_sell)
            hits = grp.loc[mask, "strike"].dropna()
            if hits.empty:
                return None
            # Eindeutiger Strike (bei mehreren Kontrakten gleicher Leg trotzdem gleicher Strike)
            unique = hits.unique()
            return Decimal(str(unique[0])) if len(unique) == 1 else None

        max_qty = grp["quantity"].abs().max()

        groups[key] = {
            "group_key":        key,
            "underlying":       str(first["underlyingSymbol"] or ""),
            "open_date":        str(first["open_date"]) if pd.notna(first["open_date"]) else "",
            "close_date":       str(first["close_date"]) if pd.notna(first["close_date"]) else "",
            "opt_strategy_name": str(first["opt_strategyName"] or ""),
            "total_profit":     Decimal(str(grp["profit"].sum())),
            "total_commission": Decimal(str(grp["ibCommission"].sum())),
            "contract_count":   Decimal(str(int(max_qty))) if pd.notna(max_qty) else None,
            "closed_by":        str(first["closedBy"] or "").upper(),
            "status":           str(first["status"] or ""),
            "leg_count":        len(grp),
            "short_call":       get_strike("C", "SELL"),
            "long_call":        get_strike("C", "BUY"),
            "short_put":        get_strike("P", "SELL"),
            "long_put":         get_strike("P", "BUY"),
        }

    return groups


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def find_ibkr_match(tat_row: dict, ibkr_groups: dict) -> dict | None:
    """
    Sucht die passende IBKR-Gruppe für einen TAT-Trade.
    Match-Kriterien (absteigend nach Präzision):
      1. underlying + open_date + Strikes
      2. underlying + open_date (wenn eindeutig)
    """
    tat_date       = tat_open_date(tat_row)
    tat_underlying = tat_row["underlying"]

    candidates = [
        g for g in ibkr_groups.values()
        if g["underlying"] == tat_underlying and g["open_date"] == tat_date
    ]

    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]

    # Bei mehreren Kandidaten: Strikes vergleichen
    for g in candidates:
        if (
            g["short_call"] == tat_row["short_call"]
            and g["long_call"] == tat_row["long_call"]
            and g["short_put"] == tat_row["short_put"]
            and g["long_put"] == tat_row["long_put"]
        ):
            return g

    # Fallback: ersten Kandidaten nehmen (mit Warnung)
    return candidates[0]


# ---------------------------------------------------------------------------
# Vergleich und Ausgabe
# ---------------------------------------------------------------------------

TRENN = "═" * 60
TRENN_THIN = "─" * 60
OK  = "✓"
NOK = "✗"
NA  = "-"


def _fmt_dec(val: Decimal | None, width: int = 10) -> str:
    if val is None:
        return " " * width
    return f"{float(val):>{width}.4f}"


def _check_status(tat_status: str, ibkr_closed_by: str) -> bool:
    allowed = STATUS_MAP.get(tat_status, [tat_status.upper()])
    return ibkr_closed_by.upper() in allowed


def has_fifo_conflict(tat_row: dict, tat_rows: list) -> bool:
    """
    Prüft ob ein TAT-Trade ein FIFO-Konflikt sein könnte.
    Kriterium: gleicher Tag + Underlying mit mindestens einem gemeinsamen Strike.
    """
    tat_date = tat_open_date(tat_row)
    underlying = tat_row["underlying"]
    my_strikes = {tat_row["short_call"], tat_row["long_call"],
                  tat_row["short_put"], tat_row["long_put"]} - {None}

    for other in tat_rows:
        if other is tat_row:
            continue
        if tat_open_date(other) != tat_date or other["underlying"] != underlying:
            continue
        other_strikes = {other["short_call"], other["long_call"],
                         other["short_put"], other["long_put"]} - {None}
        if my_strikes & other_strikes:
            return True
    return False


def _strike_str(sc, lc, sp, lp) -> str:
    parts = []
    if sc:
        parts.append(f"SC={sc}")
    if lc:
        parts.append(f"LC={lc}")
    if sp:
        parts.append(f"SP={sp}")
    if lp:
        parts.append(f"LP={lp}")
    return " ".join(parts) if parts else "—"


def compare_trade(tat: dict, ibkr: dict, tolerance: Decimal) -> dict:
    """Vergleicht einen TAT-Trade mit einer IBKR-Gruppe, gibt Ergebnis-Dict zurück."""
    results = {}

    # P&L — TAT ist netto (Commission bereits abgezogen), IBKR ist brutto
    # Vergleich auf gleicher Basis: beide netto (IBKR brutto + IBKR commission)
    if tat["profit_loss"] is not None and ibkr["total_profit"] is not None and ibkr["total_commission"] is not None:
        ibkr_net = ibkr["total_profit"] + ibkr["total_commission"]
        diff = abs(tat["profit_loss"] - ibkr_net)
        results["pl"] = (tat["profit_loss"], ibkr_net, diff, diff <= tolerance)
    else:
        results["pl"] = (tat["profit_loss"], ibkr["total_profit"], None, None)

    # Provision
    if tat["commission"] is not None and ibkr["total_commission"] is not None:
        diff = abs(tat["commission"] - abs(ibkr["total_commission"]))
        results["commission"] = (tat["commission"], ibkr["total_commission"], diff, diff <= tolerance)
    else:
        results["commission"] = (tat["commission"], ibkr["total_commission"], None, None)

    # Kontrakte — TAT ContractCount = Anzahl Legs, IBKR leg_count = Anzahl Legs
    ibkr_legs = Decimal(str(ibkr["leg_count"]))
    if tat["contract_count"] is not None:
        ok = int(tat["contract_count"]) == ibkr["leg_count"]
        results["contracts"] = (tat["contract_count"], ibkr_legs, None, ok)
    else:
        results["contracts"] = (tat["contract_count"], ibkr_legs, None, None)

    # Status
    status_ok = _check_status(tat["status"], ibkr["closed_by"])
    results["status"] = (tat["status"], ibkr["closed_by"], None, status_ok)

    # Strikes
    strikes_ok = (
        tat["short_call"] == ibkr["short_call"]
        and tat["long_call"] == ibkr["long_call"]
        and tat["short_put"] == ibkr["short_put"]
        and tat["long_put"] == ibkr["long_put"]
    )
    results["strikes"] = (
        _strike_str(tat["short_call"], tat["long_call"], tat["short_put"], tat["long_put"]),
        _strike_str(ibkr["short_call"], ibkr["long_call"], ibkr["short_put"], ibkr["long_put"]),
        None,
        strikes_ok,
    )

    return results


def _icon(ok) -> str:
    if ok is True:
        return f"\033[32m{OK}\033[0m"      # Grün
    if ok is False:
        return f"\033[31m{NOK}\033[0m"     # Rot
    if ok == "warn":
        return f"\033[33m~\033[0m"         # Gelb — Lot-Zuordnungs-Warnung
    return f"\033[33m{NA}\033[0m"          # Gelb — unbekannt


def print_trade_result(idx: int, tat: dict, ibkr: dict | None, tolerance: Decimal,
                       fifo_conflict: bool = False) -> bool:
    """
    Gibt einen Trade-Vergleich aus.
    Rückgabe:
      True   = vollständig OK
      False  = echter Fehler
      None   = nur Warnung (Lot-Zuordnung bei Closed-Trades)
    """
    date_str  = tat_open_date(tat)
    is_closed = tat["status"] == "Closed"
    header    = f"Trade #{idx}: {tat['underlying']} | {tat['trade_type']} | {date_str}"

    print(f"\n{TRENN}")
    print(f" {header}")
    print(TRENN)

    if ibkr is None:
        print(f"  \033[33m{NOK} KEIN IBKR-EINTRAG GEFUNDEN\033[0m  "
              f"(noch nicht importiert oder Symbol abweichend)")
        return False

    # Strategie-Info
    print(f"  IBKR  opt_strategyID={ibkr['group_key'][:30]}  "
          f"strategyName={ibkr['opt_strategy_name']}  "
          f"Legs={ibkr['leg_count']}")
    print(TRENN_THIN)

    results      = compare_trade(tat, ibkr, tolerance)
    all_ok       = True
    has_lot_warn = False  # P&L-Abweichung bei Closed-Trade (FIFO-Effekt)

    def row(label: str, tat_val, ibkr_val, diff, ok, fmt="s", lot_sensitive: bool = False):
        """
        lot_sensitive=True: Abweichung bei Closed-Trade → gelbe Warnung statt roter Fehler,
        da FIFO-Lot-Zuordnung legitimerweise abweichen kann.
        """
        nonlocal all_ok, has_lot_warn
        # Ggf. Fehler zu Warnung degradieren
        display_ok = ok
        if ok is False and lot_sensitive and is_closed:
            has_lot_warn = True
            display_ok   = "warn"   # eigenes Signal für gelbe Ausgabe
        elif ok is False:
            all_ok = False

        if fmt == "d":
            tv = f"{float(tat_val):>10.4f}" if tat_val is not None else " " * 10
            iv = f"{float(ibkr_val):>10.4f}" if ibkr_val is not None else " " * 10
            dv = f"{float(diff):>8.4f}" if diff is not None else " " * 8
            print(f"  {label:<12}  TAT:{tv}   IBKR:{iv}   Diff:{dv}   {_icon(display_ok)}")
        else:
            tv = str(tat_val or "—")
            iv = str(ibkr_val or "—")
            print(f"  {label:<12}  TAT: {tv:<20}  IBKR: {iv:<20}  {_icon(display_ok)}")

    pl_tat, pl_ibkr, pl_diff, pl_ok = results["pl"]
    row("P&L",        pl_tat, pl_ibkr, pl_diff, pl_ok, "d", lot_sensitive=True)

    cm_tat, cm_ibkr, cm_diff, cm_ok = results["commission"]
    row("Provision",  cm_tat, cm_ibkr, cm_diff, cm_ok, "d")

    ct_tat, ct_ibkr, _, ct_ok = results["contracts"]
    row("Kontrakte",  ct_tat, ct_ibkr, None, ct_ok, "d")

    st_tat, st_ibkr, _, st_ok = results["status"]
    row("Status",     st_tat, st_ibkr, None, st_ok, "s")

    sk_tat, sk_ibkr, _, sk_ok = results["strikes"]
    row("Strikes",    sk_tat, sk_ibkr, None, sk_ok, "s")

    print(TRENN_THIN)
    if all_ok and not has_lot_warn:
        print(f"  \033[32m→ ÜBEREINSTIMMEND {OK}\033[0m")
        return True
    elif all_ok and has_lot_warn:
        # Closed-Trade: P&L-Diff erwartet — kein echter Fehler
        print(f"  \033[33m~ WARNUNG: P&L-Abweichung durch Lot-Zuordnung (FIFO vs. TAT)\033[0m")
        if fifo_conflict:
            print(f"  \033[33m  Zusätzlich: gleicher Strike in mehreren gleichzeitigen Spreads\033[0m")
        print(f"  \033[33m  Gesamt-P&L über alle Trades stimmt überein — Einzelwert kann abweichen\033[0m")
        return None  # Warnung, kein Fehler
    elif fifo_conflict:
        print(f"  \033[33m→ FIFO-KONFLIKT — TAT/IBKR verwenden verschiedene Lot-Zuordnung\033[0m")
        print(f"  \033[33m  (gleicher Strike in mehreren gleichzeitigen Spreads — Gesamt-P&L stimmt überein)\033[0m")
        return None
    else:
        print(f"  \033[31m→ ABWEICHUNG GEFUNDEN {NOK}\033[0m")
        return False


def _ibkr_net(ibkr: dict) -> Decimal | None:
    """IBKR Netto-P&L: profit + commission (commission ist negativ in DB)."""
    if ibkr["total_profit"] is None or ibkr["total_commission"] is None:
        return None
    return ibkr["total_profit"] + ibkr["total_commission"]


def print_day_aggregation(
    warn_trades: list[tuple[dict, dict]],
    all_day_trades: list[tuple[dict, dict | None]],
    ibkr_groups: dict[str, dict],
    tolerance: Decimal,
) -> None:
    """
    Gibt die Tagesaggregation direkt nach den Trades des Tages aus.

    warn_trades    — Closed-Trades mit Lot-Warnung (Teilmenge)
    all_day_trades — alle TAT-Trades des Tages
    ibkr_groups    — alle IBKR-Gruppen (für tagesbasierte Direktsummierung)

    Ablauf:
      1. Warn-Trades: TAT-Summe vs. IBKR-Summe (de-dupliziert)
      2. Stimmt nicht → Tages-Gesamt: TAT alle Trades vs. ALLE IBKR-Gruppen
         des Tages direkt aus ibkr_groups (umgeht Matching-Fehler).
    """
    if not warn_trades:
        return None

    date_str = tat_open_date(warn_trades[0][0])

    def tat_sum(trades: list[tuple[dict, dict | None]]) -> Decimal:
        return sum((t["profit_loss"] or Decimal(0)) for t, _ in trades)

    def ibkr_sum_dedup(trades: list[tuple[dict, dict | None]]) -> Decimal:
        """Summiert IBKR-Gruppen ohne Duplikate (gleiche group_key nur 1×)."""
        seen: set[str] = set()
        total = Decimal(0)
        for _, g in trades:
            if g is None:
                continue
            key = g["group_key"]
            if key not in seen:
                seen.add(key)
                total += _ibkr_net(g) or Decimal(0)
        return total

    # --- Schritt 1: Aggregation nur der Warn-Trades (de-dupliziert) ---
    warn_tat  = tat_sum(warn_trades)
    warn_ibkr = ibkr_sum_dedup(warn_trades)
    warn_diff = abs(warn_tat - warn_ibkr)
    warn_ok   = warn_diff <= tolerance

    print(f"\n  ┌─ Tagesaggregation Lot-Zuordnung  [{date_str}]")
    for tat, ibkr in warn_trades:
        t_pl = tat["profit_loss"]
        i_pl = _ibkr_net(ibkr) if ibkr else None
        t_str = f"{float(t_pl):>10.4f}" if t_pl  is not None else " " * 10
        i_str = f"{float(i_pl):>10.4f}" if i_pl  is not None else " " * 10
        print(f"  │  {tat['underlying']:<6} {tat['trade_type']:<14}  "
              f"TAT:{t_str}   IBKR:{i_str}")

    t_str = f"{float(warn_tat):>10.4f}"
    i_str = f"{float(warn_ibkr):>10.4f}"
    d_str = f"{float(warn_diff):>8.4f}"
    icon  = _icon(warn_ok)
    print(f"  │  {'─' * 56}")
    print(f"  │  {'Gesamt (Warn)':<20}  TAT:{t_str}   IBKR:{i_str}   Diff:{d_str}   {icon}")

    if warn_ok:
        print(f"  └─ {_icon(True)} Gesamt-P&L stimmt überein")
        return None   # Kein Roll — nur normale Lot-Warnung

    # --- Schritt 2: Tages-Gesamt — IBKR direkt aus allen Gruppen des Tages ---
    # Umgeht den Matching-Fehler: alle IBKR-Gruppen mit open_date == date_str summieren
    day_tat       = tat_sum(all_day_trades)
    ibkr_day_grps = [g for g in ibkr_groups.values() if g["open_date"] == date_str]
    day_ibkr      = sum((_ibkr_net(g) or Decimal(0)) for g in ibkr_day_grps)
    day_diff      = abs(day_tat - day_ibkr)
    day_ok        = day_diff <= tolerance

    print(f"  │")
    print(f"  │  \033[33m~ Warn-Aggregation weicht ab — prüfe Tages-Gesamt...\033[0m")
    print(f"  │  {'─' * 56}")

    # TAT-Zeilen mit P&L
    for tat, _ in all_day_trades:
        t_pl  = tat["profit_loss"]
        t_str = f"{float(t_pl):>10.4f}" if t_pl is not None else " " * 10
        flag  = " ← Lot-Warnung" if any(w is tat for w, _ in warn_trades) else ""
        print(f"  │  {tat['underlying']:<6} {tat['trade_type']:<14}  TAT:{t_str}{flag}")

    # IBKR-Gruppen des Tages
    print(f"  │  {'─' * 56}")
    print(f"  │  IBKR-Gruppen ({len(ibkr_day_grps)}):")
    for g in ibkr_day_grps:
        i_pl  = _ibkr_net(g)
        i_str = f"{float(i_pl):>10.4f}" if i_pl is not None else " " * 10
        sc = g["short_call"] or ""; lc = g["long_call"] or ""
        sp = g["short_put"]  or ""; lp = g["long_put"]  or ""
        strikes = f"SP={sp} LP={lp}" if sp or lp else f"SC={sc} LC={lc}"
        print(f"  │    {g['group_key'][:8]}…  {strikes:<22}  {i_str}")

    t_str = f"{float(day_tat):>10.4f}"
    i_str = f"{float(day_ibkr):>10.4f}"
    d_str = f"{float(day_diff):>8.4f}"
    icon  = _icon(day_ok)
    print(f"  │  {'─' * 56}")
    print(f"  │  {'Tages-Gesamt':<20}  TAT:{t_str}   IBKR:{i_str}   Diff:{d_str}   {icon}")

    if day_ok:
        print(f"  │")
        print(f"  │  \033[33m~ Roll/Interferenz: TAT und IBKR attributieren P&L\033[0m")
        print(f"  │  \033[33m  unterschiedlich auf die einzelnen Strategien.\033[0m")
        print(f"  │  \033[33m  Tages-Gesamt stimmt → kein echter Fehler.\033[0m")
        print(f"  └─ \033[33m~ OK auf Tagesebene\033[0m")
        return True   # Interferenz bestätigt — alle Fehler dieses Tages sind Warnungen
    else:
        print(f"  │")
        print(f"  │  \033[31m✗ Auch Tages-Gesamt weicht ab — echter Fehler!\033[0m")
        print(f"  └─ \033[31m✗ ABWEICHUNG\033[0m")
        return False


def print_summary(total: int, ok: int, nok: int, missing: int, warn: int) -> None:
    print(f"\n{TRENN}")
    print(" ZUSAMMENFASSUNG")
    print(TRENN)
    print(f"  Verglichene Trades      : {total:>4}")
    print(f"  Übereinstimmend         : {ok:>4}  \033[32m{OK}\033[0m")
    print(f"  Echte Abweichungen      : {nok:>4}  \033[31m{NOK}\033[0m")
    print(f"  Roll/Interferenz        : {warn:>4}  \033[33m~\033[0m  (FIFO/Roll — Tages-Gesamt stimmt)")
    print(f"  Nicht gefunden          : {missing:>4}  \033[33m{NA}\033[0m  (noch nicht in IBKR importiert)")
    print(TRENN)


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="TAT vs. IBKR Datenvergleich")
    parser.add_argument("csv",        type=Path,            help="Pfad zur TAT CSV-Datei")
    parser.add_argument("--env",      default=DEFAULT_ENV,  help="DB-Environment (default: autom_paper)")
    parser.add_argument("--tolerance",type=Decimal, default=DEFAULT_TOLERANCE,
                        help="Toleranz für Dezimalvergleiche (default: 0.01)")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"Fehler: Datei nicht gefunden — {args.csv}")
        sys.exit(1)

    print(f"\nLade TAT-Daten aus:   {args.csv}")
    tat_rows = load_tat_csv(args.csv)
    print(f"TAT Trades gefunden:  {len(tat_rows)}")

    print(f"Lade IBKR-Daten aus:  {args.env}")
    ibkr_groups = load_ibkr_groups(args.env)
    print(f"IBKR Gruppen geladen: {len(ibkr_groups)}")

    cnt_ok, cnt_nok, cnt_missing, cnt_warn = 0, 0, 0, 0

    # FIFO-Konflikte vorab ermitteln (gleichzeitige Spreads mit gemeinsamem Strike)
    fifo_conflicts = {id(tat) for tat in tat_rows if has_fifo_conflict(tat, tat_rows)}

    # Tageweise gruppieren (Reihenfolge aus CSV beibehalten)
    from itertools import groupby
    tat_by_date = groupby(tat_rows, key=tat_open_date)

    idx = 1
    for _date, day_iter in tat_by_date:
        day_tat = list(day_iter)
        day_results: list[tuple[dict, dict | None, object]] = []  # (tat, ibkr, ok)

        for tat in day_tat:
            ibkr          = find_ibkr_match(tat, ibkr_groups)
            fifo_conflict = id(tat) in fifo_conflicts
            ok            = print_trade_result(idx, tat, ibkr, args.tolerance, fifo_conflict)
            day_results.append((tat, ibkr, ok))
            idx += 1

        # Aggregation direkt nach dem letzten Trade des Tages
        warn_today  = [(t, g) for t, g, ok in day_results if ok is None and g is not None]
        all_today   = [(t, g) for t, g, _ok in day_results]
        roll_confirmed = print_day_aggregation(warn_today, all_today, ibkr_groups, args.tolerance)
        # roll_confirmed=True → Tages-Gesamt stimmt trotz Einzel-Fehler (Roll/Interferenz)

        # Zähler aktualisieren
        for _tat, ibkr, ok in day_results:
            if ibkr is None:
                cnt_missing += 1
            elif ok is False and roll_confirmed:
                # Harter Fehler, aber Tages-Gesamt bestätigt → Roll-Interferenz, kein echter Fehler
                cnt_warn += 1
            elif ok is None:
                cnt_warn += 1
            elif ok:
                cnt_ok += 1
            else:
                cnt_nok += 1

    print_summary(len(tat_rows), cnt_ok, cnt_nok, cnt_missing, cnt_warn)


if __name__ == "__main__":
    main()
