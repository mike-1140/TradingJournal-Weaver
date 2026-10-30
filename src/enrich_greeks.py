"""
Pipeline-Schritt "enrich": Delta / IV / IVR / IVP für Options-Trades nachträglich rekonstruieren.
======================================================================================================
Die Flex Query liefert zu einer Options-Ausführung weder Griechen noch implizite Volatilität noch
den Kurs des Basiswerts. Über die TWS-API (ib_async) lassen sich diese Werte aber nachträglich
bestimmen — es muss beim Trade nichts mitgeschrieben werden:

  1. Kurs des Basiswerts zur Ausführungsminute (historische 1-Minuten-Kurse)
  2. IV der Option aus dem tatsächlichen Ausführungspreis (Black-Scholes, Nullstelle) → Delta
  3. IV-Historie des Basiswerts (Tageswerte) → IVR / IVP am Handelstag

Ergebnisse: Tabelle trade_greeks (Schlüssel tradeID), IV-Tageswerte zwischengespeichert in
iv_history. Beide sind abgeleitete Daten — nicht in reset_IBKR_DB.py; dieser Schritt legt sie bei
Bedarf selbst an und berechnet nach einem Neuaufbau einfach neu.

Verbindung NUR LESEND (readonly=True, keine Order-Aufrufe), eigene clientId (TWS_CLIENT_ID).
Ist die TWS / das IB Gateway nicht erreichbar, wird der Schritt übersprungen (Exit-Code 0) und
beim nächsten Lauf nachgeholt.

Aufruf:
  python -m src.enrich_greeks                               # alle Ziele aus pipeline.toml, letzte 14 Tage
  python -m src.enrich_greeks paper mike_                   # einzelnes Ziel
  python -m src.enrich_greeks --seit 2025-01-01 --max 300   # rückwirkend, in Etappen
  python -m src.enrich_greeks --fehler-wiederholen          # Trades mit gespeichertem Fehler erneut
"""

import argparse
import math
import sys
import time as time_mod
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from scipy.optimize import brentq
from scipy.stats import norm
from sqlalchemy import text

from src.config import (
    GREEKS_RATE, GREEKS_TRADE_TZ, TABLE_IV_HISTORY, TABLE_PREFIX, TABLE_TRADE_GREEKS, TABLE_TRADES_RAW,
    TWS_CLIENT_ID, TWS_HOST, TWS_PORT, get_engine, load_active_targets,
)
from src.logger_setup import setup_logging
from src.trade_enums import TradeStatus
from src.utils.div_utils import to_decimal
from src.utils.path_utils import get_project_root

logger, _ = setup_logging("my_app", level="simple", log_file=get_project_root() / "log/app.log")

ET = ZoneInfo("America/New_York")
DEFAULT_DAYS_BACK = 14
DEFAULT_MAX_TRADES = 200
MIN_IV_DAYS = 20                 # weniger Tageswerte → IVR/IVP nicht aussagekräftig
REQUEST_PAUSE_SECONDS = 1.0      # Rücksicht auf die Abfragegrenzen von IBKR
EVENT_STATUSES = {TradeStatus.EXPIRED.value, TradeStatus.ASSIGNED.value, TradeStatus.CASH_SETTLED.value}

# Indizes: Optionssymbol/Underlying → (Index-Symbol, Börse); alles andere gilt als Aktie/ETF (SMART)
INDEX_MAP = {
    "SPX": ("SPX", "CBOE"), "SPXW": ("SPX", "CBOE"), "XSP": ("XSP", "CBOE"),
    "NDX": ("NDX", "NASDAQ"), "NDXP": ("NDX", "NASDAQ"), "RUT": ("RUT", "RUSSELL"),
    "RUTW": ("RUT", "RUSSELL"), "VIX": ("VIX", "CBOE"), "VIXW": ("VIX", "CBOE"),
}


# =====================================================================================
# Rechenteil (ohne TWS/DB, getestet)
# =====================================================================================

def _d1_d2(S, K, T, sigma, rate):
    d1 = (math.log(S / K) + (rate + sigma ** 2 / 2) * T) / (sigma * math.sqrt(T))
    return d1, d1 - sigma * math.sqrt(T)


def bs_price(S, K, T, sigma, put, rate=GREEKS_RATE):
    """Black-Scholes-Preis (europäisch, ohne Dividende)."""
    d1, d2 = _d1_d2(S, K, T, sigma, rate)
    if put:
        return K * math.exp(-rate * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    return S * norm.cdf(d1) - K * math.exp(-rate * T) * norm.cdf(d2)


def bs_delta(S, K, T, sigma, put, rate=GREEKS_RATE):
    d1, _ = _d1_d2(S, K, T, sigma, rate)
    return norm.cdf(d1) - 1 if put else norm.cdf(d1)


def implied_vol(price, S, K, T, put, rate=GREEKS_RATE):
    """IV aus dem Optionspreis; None, wenn kein Wert passt (z. B. Preis unter innerem Wert)."""
    if not price or price <= 0 or not S or S <= 0 or T <= 0:
        return None
    try:
        return brentq(lambda s: bs_price(S, K, T, s, put, rate) - price, 1e-4, 5.0)
    except ValueError:
        return None


def year_fraction(trade_dt: datetime, expiry: date) -> float:
    """Restlaufzeit in Jahren bis Verfall 16:00 New York (beide Zeitpunkte zeitzonenbewusst)."""
    expiry_dt = datetime.combine(expiry, time(16, 0), ET)
    return (expiry_dt - trade_dt).total_seconds() / (365 * 24 * 3600)


def iv_rank_percentile(values):
    """Aus IV-Tageswerten (ältester zuerst, letzter = Stichtag): (IV, IVR, IVP) oder None."""
    vals = [v for v in values if v and v > 0]
    if len(vals) < MIN_IV_DAYS:
        return None
    cur, lo, hi = vals[-1], min(vals), max(vals)
    ivr = (cur - lo) / (hi - lo) * 100 if hi > lo else None
    ivp = sum(v < cur for v in vals[:-1]) / (len(vals) - 1) * 100
    return cur, ivr, ivp


def underlying_spec(underlying_symbol: str, symbol: str):
    """('index', Symbol, Börse) oder ('stock', Symbol, 'SMART') für den Basiswert."""
    base = (underlying_symbol or "").strip().upper() or (symbol or "").split()[0].upper()
    root = (symbol or "").split()[0].upper()
    for key in (root, base):
        if key in INDEX_MAP:
            sym, exch = INDEX_MAP[key]
            return "index", sym, exch
    return "stock", base, "SMART"


def is_candidate(row: dict) -> bool:
    """Options-Trade mit echtem Ausführungspreis — keine Verfall-/Zuteilungs-/Barausgleichs-Buchung."""
    return (row.get("assetCategory") == "OPT"
            and (row.get("tradePrice") or 0) > 0
            and (row.get("status") or "") not in EVENT_STATUSES)


def compute_greeks(row: dict, source, tz: ZoneInfo, rate=GREEKS_RATE) -> dict:
    """Berechnet die Werte für einen Trade. source liefert underlying_price() und iv_values()."""
    kind, usym, exch = underlying_spec(row.get("underlyingSymbol"), row.get("symbol"))
    trade_dt = row["dateTime"]
    trade_dt = trade_dt.replace(tzinfo=tz) if trade_dt.tzinfo is None else trade_dt
    expiry = row["expiry"].date() if isinstance(row["expiry"], datetime) else row["expiry"]
    put = str(row.get("putCall")) == "P"
    result = {"tradeID": str(row["tradeID"]), "underlying": usym, "trade_datetime": trade_dt,
              "underlying_price": None, "option_iv": None, "delta": None,
              "underlying_iv": None, "ivr": None, "ivp": None, "iv_days": 0, "error": None}
    errors = []

    S = source.underlying_price(kind, usym, exch, trade_dt.astimezone(ET))
    if S is None:
        errors.append("kein Basiswert-Kurs")
    else:
        result["underlying_price"] = S
        T = year_fraction(trade_dt.astimezone(ET), expiry)
        iv = implied_vol(float(row["tradePrice"]), S, float(row["strike"]), T, put, rate)
        if iv is None:
            errors.append("IV nicht bestimmbar")
        else:
            result["option_iv"] = iv
            result["delta"] = bs_delta(S, float(row["strike"]), T, iv, put, rate)

    values = source.iv_values(kind, usym, exch, trade_dt.astimezone(ET).date())
    result["iv_days"] = len(values)
    stats = iv_rank_percentile(values)
    if stats is None:
        errors.append(f"zu wenig IV-Historie ({len(values)} Tage)")
    else:
        result["underlying_iv"], result["ivr"], result["ivp"] = stats

    result["error"] = "; ".join(errors) or None
    return result


# =====================================================================================
# TWS-Anbindung (nur lesend)
# =====================================================================================

def connect_tws():
    """IB-Verbindung oder None, wenn keine TWS / kein IB Gateway erreichbar ist."""
    from ib_async import IB   # erst hier importieren: Tests und Läufe ohne TWS brauchen es nicht
    ib = IB()
    try:
        ib.connect(TWS_HOST, TWS_PORT, clientId=TWS_CLIENT_ID, readonly=True, timeout=10)
    except (ConnectionRefusedError, TimeoutError, OSError) as e:
        logger.info(f"TWS/IB Gateway nicht erreichbar ({TWS_HOST}:{TWS_PORT}, {e.__class__.__name__}) — "
                    f"Schritt enrich übersprungen, wird beim nächsten Lauf nachgeholt")
        return None
    return ib


class TwsSource:
    """Liefert Basiswert-Kurse und IV-Tageswerte; IV-Werte werden in iv_history zwischengespeichert."""

    def __init__(self, ib, conn, prefix):
        self.ib, self.conn, self.prefix = ib, conn, prefix
        self._contracts, self._prices, self._covered = {}, {}, {}

    def _contract(self, kind, usym, exch):
        key = (kind, usym, exch)
        if key not in self._contracts:
            from ib_async import Index, Stock
            c = Index(usym, exch, "USD") if kind == "index" else Stock(usym, exch, "USD")
            self.ib.qualifyContracts(c)
            self._contracts[key] = c
        return self._contracts[key]

    def underlying_price(self, kind, usym, exch, when):
        key = (usym, when.replace(second=0, microsecond=0))
        if key not in self._prices:
            bars = self.ib.reqHistoricalData(
                self._contract(kind, usym, exch), endDateTime=when + timedelta(minutes=1),
                durationStr="1800 S", barSizeSetting="1 min", whatToShow="TRADES",
                useRTH=True, formatDate=2)
            time_mod.sleep(REQUEST_PAUSE_SECONDS)
            bars = [b for b in bars if b.date <= when]
            self._prices[key] = float(bars[-1].close) if bars else None
        return self._prices[key]

    def _ensure_iv(self, kind, usym, exch, day):
        """Sorgt dafür, dass iv_history das Jahr vor `day` für den Basiswert enthält."""
        start = day - timedelta(days=366)
        lo, hi = self._covered.get(usym, (None, None))
        if lo is not None and lo <= start and hi >= day:
            return
        row = self.conn.execute(text(
            f"SELECT MIN(iv_date), MAX(iv_date) FROM `{self.prefix}{TABLE_IV_HISTORY}` WHERE underlying = :u"),
            {"u": usym}).first()
        db_lo, db_hi = (row[0], row[1]) if row else (None, None)
        if db_lo is not None and db_lo <= start + timedelta(days=7) and db_hi >= day:
            self._covered[usym] = (db_lo, db_hi)
            return
        years = max(1, math.ceil(((date.today() - start).days + 7) / 365))
        bars = self.ib.reqHistoricalData(
            self._contract(kind, usym, exch), endDateTime="", durationStr=f"{years} Y",
            barSizeSetting="1 day", whatToShow="OPTION_IMPLIED_VOLATILITY", useRTH=True, formatDate=1)
        time_mod.sleep(REQUEST_PAUSE_SECONDS)
        for b in bars:
            if b.close and b.close > 0:
                self.conn.execute(text(
                    f"INSERT INTO `{self.prefix}{TABLE_IV_HISTORY}` (underlying, iv_date, iv) VALUES (:u, :d, :iv) "
                    f"ON DUPLICATE KEY UPDATE iv = VALUES(iv)"),
                    {"u": usym, "d": b.date, "iv": to_decimal(round(b.close, 6))})
        if bars:
            self._covered[usym] = (min(b.date for b in bars), max(b.date for b in bars))

    def iv_values(self, kind, usym, exch, day):
        self._ensure_iv(kind, usym, exch, day)
        rows = self.conn.execute(text(
            f"SELECT iv FROM `{self.prefix}{TABLE_IV_HISTORY}` WHERE underlying = :u "
            f"AND iv_date > :start AND iv_date <= :day ORDER BY iv_date"),
            {"u": usym, "start": day - timedelta(days=365), "day": day}).fetchall()
        return [float(r[0]) for r in rows]


# =====================================================================================
# Datenbank
# =====================================================================================

def ensure_tables(conn, prefix):
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS `{prefix}{TABLE_IV_HISTORY}` (
            underlying VARCHAR(20) NOT NULL,
            iv_date DATE NOT NULL,
            iv DECIMAL(10,6) NOT NULL,
            PRIMARY KEY (underlying, iv_date)
        ) DEFAULT CHARSET=utf8mb4"""))
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS `{prefix}{TABLE_TRADE_GREEKS}` (
            tradeID VARCHAR(50) NOT NULL PRIMARY KEY,
            environment VARCHAR(20) NOT NULL,
            symbol VARCHAR(50) NULL,
            underlying VARCHAR(20) NULL,
            trade_datetime DATETIME NULL,
            underlying_price DECIMAL(14,4) NULL,
            option_iv DECIMAL(10,6) NULL,
            delta DECIMAL(8,5) NULL,
            underlying_iv DECIMAL(10,6) NULL,
            ivr DECIMAL(6,2) NULL,
            ivp DECIMAL(6,2) NULL,
            iv_days INT NOT NULL DEFAULT 0,
            error VARCHAR(255) NULL,
            computed_at DATETIME NOT NULL
        ) DEFAULT CHARSET=utf8mb4"""))


def load_candidates(conn, prefix, env_up, since: date, retry_errors: bool, limit: int):
    retry = "OR g.error IS NOT NULL" if retry_errors else ""
    rows = conn.execute(text(f"""
        SELECT r.tradeID, r.symbol, r.underlyingSymbol, r.assetCategory, r.putCall, r.strike, r.expiry,
               r.dateTime, r.tradePrice, r.status
        FROM `{prefix}{TABLE_TRADES_RAW}` r
        LEFT JOIN `{prefix}{TABLE_TRADE_GREEKS}` g ON g.tradeID = r.tradeID
        WHERE r.environment = :env AND r.assetCategory = 'OPT' AND r.tradePrice > 0
          AND r.dateTime >= :since AND (g.tradeID IS NULL {retry})
        ORDER BY r.dateTime DESC"""), {"env": env_up, "since": since}).mappings().all()
    seen, out = set(), []
    for r in rows:   # gleiche tradeID kann in trades_raw doppelt vorkommen (Strategie-Legs)
        r = dict(r)
        if is_candidate(r) and r["tradeID"] not in seen:
            seen.add(r["tradeID"])
            out.append(r)
    return out[:limit]


def save_result(conn, prefix, env_up, row, res):
    def dec(v, nd):
        return to_decimal(round(v, nd)) if v is not None else None
    conn.execute(text(f"""
        INSERT INTO `{prefix}{TABLE_TRADE_GREEKS}`
            (tradeID, environment, symbol, underlying, trade_datetime, underlying_price, option_iv, delta,
             underlying_iv, ivr, ivp, iv_days, error, computed_at)
        VALUES (:tid, :env, :sym, :und, :tdt, :sp, :oiv, :dl, :uiv, :ivr, :ivp, :days, :err, :now)
        ON DUPLICATE KEY UPDATE underlying=VALUES(underlying), trade_datetime=VALUES(trade_datetime),
            underlying_price=VALUES(underlying_price), option_iv=VALUES(option_iv), delta=VALUES(delta),
            underlying_iv=VALUES(underlying_iv), ivr=VALUES(ivr), ivp=VALUES(ivp), iv_days=VALUES(iv_days),
            error=VALUES(error), computed_at=VALUES(computed_at)"""),
        {"tid": res["tradeID"], "env": env_up, "sym": row["symbol"], "und": res["underlying"],
         "tdt": row["dateTime"], "sp": dec(res["underlying_price"], 4), "oiv": dec(res["option_iv"], 6),
         "dl": dec(res["delta"], 5), "uiv": dec(res["underlying_iv"], 6), "ivr": dec(res["ivr"], 2),
         "ivp": dec(res["ivp"], 2), "days": res["iv_days"], "err": (res["error"] or None) and res["error"][:255],
         "now": datetime.now()})


# =====================================================================================
# Ablauf
# =====================================================================================

def enrich_target(ib, environment, prefix, since, retry_errors, limit):
    env_up = environment.upper()
    tz = ZoneInfo(GREEKS_TRADE_TZ)
    with get_engine(environment).begin() as conn:
        ensure_tables(conn, prefix)
        candidates = load_candidates(conn, prefix, env_up, since, retry_errors, limit)
        if not candidates:
            logger.info(f"[{env_up} / {prefix}] keine neuen Options-Trades seit {since}")
            return 0, 0
        logger.info(f"[{env_up} / {prefix}] {len(candidates)} Options-Trade(s) werden angereichert")
        source = TwsSource(ib, conn, prefix)
        ok = 0
        for row in candidates:
            try:
                res = compute_greeks(row, source, tz)
            except Exception as e:  # noqa: BLE001 - ein Trade darf den Lauf nicht abbrechen
                res = {"tradeID": str(row["tradeID"]), "underlying": None, "underlying_price": None,
                       "option_iv": None, "delta": None, "underlying_iv": None, "ivr": None, "ivp": None,
                       "iv_days": 0, "error": f"{e.__class__.__name__}: {e}"}
            save_result(conn, prefix, env_up, row, res)
            ok += res["error"] is None
        logger.info(f"[{env_up} / {prefix}] fertig: {ok} vollständig, {len(candidates) - ok} mit Hinweis "
                    f"(Spalte error)")
        return ok, len(candidates) - ok


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Delta/IV/IVR/IVP für Options-Trades über die TWS-API")
    p.add_argument("environment", nargs="?")
    p.add_argument("prefix", nargs="?")
    p.add_argument("--seit", help="ab diesem Datum (JJJJ-MM-TT), Standard: letzte 14 Tage")
    p.add_argument("--max", type=int, default=DEFAULT_MAX_TRADES, help="höchstens so viele Trades je Ziel")
    p.add_argument("--fehler-wiederholen", action="store_true", help="Trades mit gespeichertem Fehler erneut")
    args = p.parse_args(argv)

    since = (datetime.strptime(args.seit, "%Y-%m-%d").date() if args.seit
             else date.today() - timedelta(days=DEFAULT_DAYS_BACK))
    if args.environment:
        targets = [{"environment": args.environment.lower(), "prefix": args.prefix or TABLE_PREFIX}]
    else:
        targets = load_active_targets()

    ib = connect_tws()
    if ib is None:
        return 0
    try:
        for t in targets:
            enrich_target(ib, t["environment"], t["prefix"], since, args.fehler_wiederholen, args.max)
    finally:
        ib.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
