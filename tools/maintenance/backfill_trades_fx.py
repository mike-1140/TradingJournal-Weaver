# tools/maintenance/backfill_trades_fx.py
"""
Fuellt trades_fx nachtraeglich mit bereits importierten FX-Umtausch-Trades.

Hintergrund: extract_trades_for_db() (src/parsers/day_trade_processor.py) hat
FX-Trades bisher NIE in trades_fx geschrieben (cashfx_table wurde initialisiert,
aber nie befuellt — Bug, behoben). Die eigentlichen Umtausch-Daten stehen aber
schon in trades_raw als Paar von assetCategory='CASH'-Zeilen (quantity=1 = "von"-
Seite, quantity=2 = "nach"-Seite, ueber linkID gepaart). Dieses Skript liest diese
Paare und traegt sie als eine Zeile pro Umtausch in trades_fx nach.

trades_raw selbst wird NICHT veraendert — reiner Zusatz-Insert in trades_fx.

Aufruf (Dry-Run ist Standard, es wird NICHTS geschrieben):
  python tools/maintenance/backfill_trades_fx.py money                # Vorschau
  python tools/maintenance/backfill_trades_fx.py money --prefix mike_ # Vorschau, expliziter Prefix
  python tools/maintenance/backfill_trades_fx.py money --prefix mike_ --execute

Optionen:
  --prefix mike_    Table-Prefix (Standard: TABLE_PREFIX aus .env)
  --execute         tatsaechlich einfuegen (Standard: Dry-Run)
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))  # xml_proj/ in sys.path

from sqlalchemy import text

from src.config import get_engine, DB_MAP, TABLE_PREFIX, TABLE_TRADES_RAW, TABLE_TRADES_FX
from src.utils.div_utils import compute_checksum
from src.logger_setup import setup_logging
from src.utils.path_utils import get_project_root


def _prefixed(prefix: str, table: str) -> str:
    return f"{prefix}{table}" if prefix else table


def find_cash_pairs(conn, t_raw: str, env_up: str) -> list[dict]:
    """Liest alle CASH-Zeilen aus trades_raw und gruppiert sie per linkID zu Paaren."""
    rows = conn.execute(text(f"""
        SELECT id, symbol, quantity, tradePrice, netCash, ibCommission,
               linkID, tradeID, ibOrderID, dateTime
        FROM `{t_raw}`
        WHERE environment = :env AND assetCategory = 'CASH'
        ORDER BY dateTime, linkID, quantity
    """), {"env": env_up}).fetchall()

    pairs: dict[str, list] = {}
    for r in rows:
        pairs.setdefault(r.linkID, []).append(r)

    result = []
    for link_id, group in pairs.items():
        if len(group) != 2:
            print(f"  WARNUNG: linkID {link_id} hat {len(group)} CASH-Zeile(n) statt 2 — uebersprungen")
            continue

        from_row = next((r for r in group if r.quantity == 1), None)
        to_row = next((r for r in group if r.quantity == 2), None)
        if not from_row or not to_row:
            print(f"  WARNUNG: linkID {link_id} hat kein passendes von/nach-Paar — uebersprungen")
            continue

        base, quote = from_row.symbol.split(".")
        result.append({
            "assetCategory": "CASH",
            "tradeID": from_row.tradeID,
            "ibOrderID": from_row.ibOrderID,
            "symbol": from_row.symbol,
            "baseCurrency": base,
            "quoteCurrency": quote,
            "baseAmount": from_row.netCash,
            "quoteAmount": to_row.netCash,
            "fxRate": from_row.tradePrice,
            "commission": from_row.ibCommission,
            "dateTime": from_row.dateTime,
        })

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Fuellt trades_fx nachtraeglich aus bereits vorhandenen CASH-Paaren in trades_raw.")
    parser.add_argument("environment", choices=list(DB_MAP.keys()))
    parser.add_argument("--prefix", default=TABLE_PREFIX,
                        help="Table-Prefix, z.B. mike_ (Standard: TABLE_PREFIX aus .env)")
    parser.add_argument("--execute", action="store_true",
                        help="Tatsaechlich einfuegen (Standard: Dry-Run)")
    args = parser.parse_args()

    env = args.environment.lower()
    env_up = env.upper()

    t_raw = _prefixed(args.prefix, TABLE_TRADES_RAW)
    t_fx = _prefixed(args.prefix, TABLE_TRADES_FX)

    log_file = get_project_root() / "log/app.log"
    logger, _ = setup_logging("backfill_trades_fx", level="simple", log_file=log_file)
    logger.info("=" * 80)
    logger.info(f"---- Backfill trades_fx — Environment: {env_up}, Praefix: '{args.prefix}', "
                f"Modus: {'EXECUTE' if args.execute else 'DRY-RUN'}")

    engine = get_engine(env)
    with engine.connect() as conn:
        candidates = find_cash_pairs(conn, t_raw, env_up)

        if not candidates:
            print(f"\nKeine CASH-Paare in {t_raw} ({env_up}) gefunden.")
            return

        # Checksum berechnen (gleiche Logik wie beim normalen Import)
        for c in candidates:
            c["checksum"] = compute_checksum(c)

        existing = conn.execute(text(f"""
            SELECT checksum FROM `{t_fx}` WHERE checksum IN :checksums
        """), {"checksums": tuple(c["checksum"] for c in candidates)}).scalars().all()
        existing = set(existing)

        new_rows = [c for c in candidates if c["checksum"] not in existing]

    print(f"\n{'Datum':<20} {'Paar':<10} {'Von-Betrag':>14} {'Nach-Betrag':>14} {'Kurs':>10}  Trade-ID")
    print("-" * 90)
    for c in candidates:
        already = " (bereits vorhanden)" if c["checksum"] not in [n["checksum"] for n in new_rows] else ""
        dt = c["dateTime"].strftime("%Y-%m-%d %H:%M:%S") if c["dateTime"] else "-"
        print(f"{dt:<20} {c['symbol']:<10} {c['baseAmount']:>14} {c['quoteAmount']:>14} "
              f"{c['fxRate']:>10}  {c['tradeID']}{already}")
    print("-" * 90)
    print(f"Gefunden: {len(candidates)} Umtausch-Paar(e), davon {len(new_rows)} neu fuer {t_fx}\n")

    if not new_rows:
        print("Nichts zu tun — alle gefundenen Paare stehen bereits in trades_fx.")
        return

    if not args.execute:
        print("DRY-RUN: Es wurde nichts geschrieben. Zum Ausfuehren --execute anhaengen.")
        return

    with engine.begin() as conn:
        for row in new_rows:
            conn.execute(text(f"""
                INSERT INTO `{t_fx}`
                    (assetCategory, tradeID, ibOrderID, symbol, baseCurrency, quoteCurrency,
                     baseAmount, quoteAmount, fxRate, commission, dateTime, environment, checksum)
                VALUES
                    (:assetCategory, :tradeID, :ibOrderID, :symbol, :baseCurrency, :quoteCurrency,
                     :baseAmount, :quoteAmount, :fxRate, :commission, :dateTime, :environment, :checksum)
            """), {**row, "environment": env_up})

    logger.info(f"Backfill abgeschlossen: {len(new_rows)} Zeile(n) in {t_fx} eingefuegt")
    print(f"Backfill abgeschlossen: {len(new_rows)} Zeile(n) in {t_fx} eingefuegt — Details siehe log/app.log")


if __name__ == "__main__":
    main()
