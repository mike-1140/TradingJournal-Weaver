# tools/maintenance/fix_symbol_mismatch.py
#
# Setzt Trades eines Symbols (inkl. Alias-Symbol) vollständig zurück:
#   - trades_raw:         processed=0
#   - trades_open:        löschen
#   - trades_close:       löschen
#   - campaign_ledger:    löschen (alle Einträge der betroffenen Kampagne)
#   - trading_campaigns:  Status auf PENDING zurücksetzen
#
# Danach kann process_ibkr_trades den Symbol-Block sauber neu verarbeiten.
#
# Aufruf (Dry-Run ist Standard, es wird NICHTS geändert):
#   .venv\Scripts\python.exe tools/maintenance/fix_symbol_mismatch.py -e paper -s BMWd -a BMW
#   .venv\Scripts\python.exe tools/maintenance/fix_symbol_mismatch.py -e paper -s BMWd -a BMW --execute

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))

import argparse
from sqlalchemy import text
import src.config as config
from src.config import (
    get_engine, DB_MAP,
    TABLE_TRADES_RAW, TABLE_TRADES_OPEN, TABLE_TRADES_CLOSE,
    TABLE_CAMPAIGN_LEDGER, TABLE_TRADING_CAMPAIGNS,
)
from src.trade_enums import CampaignStatus
from src.logger_setup import setup_logging
from src.utils.path_utils import get_project_root


def _prefixed(prefix: str, table: str) -> str:
    return f"{prefix}{table}" if prefix else table


def diagnose(conn, env: str, symbols: list[str], prefix: str) -> dict:
    """Zeigt den aktuellen Zustand aller betroffenen Datensätze."""
    placeholders = ", ".join(f":s{i}" for i in range(len(symbols)))
    sym_params = {f"s{i}": s for i, s in enumerate(symbols)}

    result = {}

    # trades_raw
    t = _prefixed(prefix, TABLE_TRADES_RAW)
    sql = text(f"""
        SELECT id, symbol, buySell, quantity, dateTime, processed
        FROM {t}
        WHERE environment = :env
          AND (symbol IN ({placeholders}) OR underlyingSymbol IN ({placeholders}))
        ORDER BY dateTime
    """)
    result["trades_raw"] = conn.execute(sql, {"env": env, **sym_params}).fetchall()

    # trades_open
    t = _prefixed(prefix, TABLE_TRADES_OPEN)
    sql = text(f"""
        SELECT id, symbol, buySell, quantity, dateTime, processed
        FROM {t}
        WHERE environment = :env
          AND (symbol IN ({placeholders}) OR underlyingSymbol IN ({placeholders}))
        ORDER BY dateTime
    """)
    result["trades_open"] = conn.execute(sql, {"env": env, **sym_params}).fetchall()

    # trades_close
    t = _prefixed(prefix, TABLE_TRADES_CLOSE)
    sql = text(f"""
        SELECT id, symbol, buySellOpen, buySellClose, quantity, dateTimeOpen, dateTimeClose
        FROM {t}
        WHERE environment = :env
          AND (symbol IN ({placeholders}) OR underlyingSymbol IN ({placeholders}))
        ORDER BY dateTimeOpen
    """)
    result["trades_close"] = conn.execute(sql, {"env": env, **sym_params}).fetchall()

    # trading_campaigns
    tc = _prefixed(prefix, TABLE_TRADING_CAMPAIGNS)
    sql = text(f"""
        SELECT id, symbol, status, start_date, end_date, closed_at
        FROM {tc}
        WHERE environment = :env
          AND symbol IN ({placeholders})
        ORDER BY id
    """)
    result["campaigns"] = conn.execute(sql, {"env": env, **sym_params}).fetchall()

    # campaign_ledger (über Kampagne)
    campaign_ids = [r.id for r in result["campaigns"]]
    if campaign_ids:
        ledger_placeholders = ", ".join(f":c{i}" for i in range(len(campaign_ids)))
        cl = _prefixed(prefix, TABLE_CAMPAIGN_LEDGER)
        sql = text(f"""
            SELECT l.id, l.campaign_id, l.source_table, l.source_id, l.action, l.symbol, l.dateTime
            FROM {cl} l
            WHERE l.campaign_id IN ({ledger_placeholders})
            ORDER BY l.dateTime
        """)
        result["campaign_ledger"] = conn.execute(
            sql, {f"c{i}": cid for i, cid in enumerate(campaign_ids)}
        ).fetchall()
    else:
        result["campaign_ledger"] = []

    return result


def apply_fix(conn, env: str, symbols: list[str], campaign_ids: list[int], prefix: str, logger) -> None:
    """Führt den Reset durch — in der richtigen FK-Reihenfolge."""
    placeholders = ", ".join(f":s{i}" for i in range(len(symbols)))
    sym_params = {f"s{i}": s for i, s in enumerate(symbols)}

    # 1. campaign_ledger löschen
    if campaign_ids:
        ledger_placeholders = ", ".join(f":c{i}" for i in range(len(campaign_ids)))
        cl = _prefixed(prefix, TABLE_CAMPAIGN_LEDGER)
        sql = text(f"DELETE FROM {cl} WHERE campaign_id IN ({ledger_placeholders})")
        r = conn.execute(sql, {f"c{i}": cid for i, cid in enumerate(campaign_ids)})
        print(f"    campaign_ledger:    {r.rowcount:>5} Zeilen gelöscht")
        logger.info(f"  campaign_ledger: {r.rowcount} Zeilen gelöscht")

    # 2. trading_campaigns auf PENDING zurücksetzen
    if campaign_ids:
        tc = _prefixed(prefix, TABLE_TRADING_CAMPAIGNS)
        ledger_placeholders = ", ".join(f":c{i}" for i in range(len(campaign_ids)))
        sql = text(f"""
            UPDATE {tc}
            SET status = '{CampaignStatus.ACTIVE.value}', end_date = NULL, closed_at = NULL
            WHERE id IN ({ledger_placeholders})
        """)
        r = conn.execute(sql, {f"c{i}": cid for i, cid in enumerate(campaign_ids)})
        print(f"    trading_campaigns:  {r.rowcount:>5} auf PENDING gesetzt")
        logger.info(f"  trading_campaigns: {r.rowcount} auf PENDING gesetzt")

    # 3. trades_close löschen
    t = _prefixed(prefix, TABLE_TRADES_CLOSE)
    sql = text(f"""
        DELETE FROM {t}
        WHERE environment = :env
          AND (symbol IN ({placeholders}) OR underlyingSymbol IN ({placeholders}))
    """)
    r = conn.execute(sql, {"env": env, **sym_params})
    print(f"    trades_close:       {r.rowcount:>5} Zeilen gelöscht")
    logger.info(f"  trades_close: {r.rowcount} Zeilen gelöscht")

    # 4. trades_open löschen
    t = _prefixed(prefix, TABLE_TRADES_OPEN)
    sql = text(f"""
        DELETE FROM {t}
        WHERE environment = :env
          AND (symbol IN ({placeholders}) OR underlyingSymbol IN ({placeholders}))
    """)
    r = conn.execute(sql, {"env": env, **sym_params})
    print(f"    trades_open:        {r.rowcount:>5} Zeilen gelöscht")
    logger.info(f"  trades_open: {r.rowcount} Zeilen gelöscht")

    # 5. trades_raw auf processed=0 zurücksetzen
    t = _prefixed(prefix, TABLE_TRADES_RAW)
    sql = text(f"""
        UPDATE {t}
        SET processed = 0
        WHERE environment = :env
          AND (symbol IN ({placeholders}) OR underlyingSymbol IN ({placeholders}))
    """)
    r = conn.execute(sql, {"env": env, **sym_params})
    print(f"    trades_raw:         {r.rowcount:>5} auf processed=0 gesetzt")
    logger.info(f"  trades_raw: {r.rowcount} auf processed=0 gesetzt")

    conn.commit()


def main():
    parser = argparse.ArgumentParser(
        description="Symbol-Reset: Trades eines Symbols + Alias komplett zurücksetzen"
    )
    parser.add_argument("--environment", "-e", default="paper", choices=list(DB_MAP.keys()),
                        help="Trading-Environment (default: paper)")
    parser.add_argument("--symbol", "-s", required=True,
                        help="Hauptsymbol (z.B. BMWd)")
    parser.add_argument("--alias", "-a", default=None,
                        help="Alias-Symbol das fälschlicherweise verwendet wurde (z.B. BMW)")
    parser.add_argument("--prefix", "-p", default=config.TABLE_PREFIX,
                        help=f"Tabellen-Prefix überschreiben (default: aus .env = '{config.TABLE_PREFIX}')")
    parser.add_argument("--execute", action="store_true",
                        help="Tatsächlich ändern (Standard: Dry-Run)")
    args = parser.parse_args()

    symbols = [args.symbol.upper()]
    if args.alias:
        symbols.append(args.alias.upper())

    env = args.environment.upper()

    log_file = get_project_root() / "log/app.log"
    logger, _ = setup_logging("fix_symbol_mismatch", level="simple", log_file=log_file)
    logger.info("=" * 80)
    logger.info(f"---- Fix Symbol Mismatch ({env}, Symbole: {', '.join(symbols)}, "
                f"Präfix: '{args.prefix}', Modus: {'EXECUTE' if args.execute else 'DRY-RUN'})")

    print()
    print("=" * 65)
    print("  FIX SYMBOL MISMATCH — Symbol-Reset")
    print("=" * 65)
    print(f"  Environment:  {env}")
    print(f"  Prefix:       '{args.prefix}'")
    print(f"  Symbole:      {', '.join(symbols)}")
    print("=" * 65)

    engine = get_engine(args.environment)

    with engine.connect() as conn:
        data = diagnose(conn, env, symbols, args.prefix)

        print("\n  --- Aktueller Zustand ---\n")

        print(f"  trades_raw ({len(data['trades_raw'])} Einträge):")
        for r in data["trades_raw"]:
            dt = str(r.dateTime)[:10] if r.dateTime else "?"
            print(f"    id={r.id:>6}  {r.symbol:<10}  {str(r.buySell):<5}  qty={r.quantity:>8}  {dt}  processed={r.processed}")

        print(f"\n  trades_open ({len(data['trades_open'])} Einträge):")
        for r in data["trades_open"]:
            dt = str(r.dateTime)[:10] if r.dateTime else "?"
            print(f"    id={r.id:>6}  {r.symbol:<10}  {str(r.buySell):<5}  qty={r.quantity:>8}  {dt}  processed={r.processed}")

        print(f"\n  trades_close ({len(data['trades_close'])} Einträge):")
        for r in data["trades_close"]:
            dt = str(r.dateTimeOpen)[:10] if r.dateTimeOpen else "?"
            print(f"    id={r.id:>6}  {r.symbol:<10}  open={str(r.buySellOpen):<5}  close={str(r.buySellClose):<5}  qty={r.quantity:>8}  {dt}")

        print(f"\n  trading_campaigns ({len(data['campaigns'])} Einträge):")
        for r in data["campaigns"]:
            print(f"    id={r.id:>6}  {r.symbol:<10}  status={r.status}  start={str(r.start_date)[:10]}")

        print(f"\n  campaign_ledger ({len(data['campaign_ledger'])} Einträge):")
        for r in data["campaign_ledger"]:
            dt = str(r.dateTime)[:10] if r.dateTime else "?"
            print(f"    id={r.id:>6}  campaign={r.campaign_id}  {str(r.action):<30}  {r.symbol:<10}  {dt}")

        total_deletes = (
            len(data["trades_open"]) +
            len(data["trades_close"]) +
            len(data["campaign_ledger"])
        )
        total_resets = len(data["trades_raw"])

        if total_deletes == 0 and total_resets == 0:
            print("\n  Nichts zu tun.\n")
            return

        campaign_ids = [r.id for r in data["campaigns"]]

        print()
        print("  Geplante Aktionen:")
        print(f"    - campaign_ledger:   {len(data['campaign_ledger'])} Zeilen löschen")
        print(f"    - trading_campaigns: {len(campaign_ids)} Kampagne(n) auf ACTIVE setzen")
        print(f"    - trades_close:      {len(data['trades_close'])} Zeilen löschen")
        print(f"    - trades_open:       {len(data['trades_open'])} Zeilen löschen")
        print(f"    - trades_raw:        {total_resets} Zeilen auf processed=0 setzen")
        print()

        if not args.execute:
            print("  DRY-RUN: Es wurde nichts geändert. Zum Ausführen --execute anhängen.\n")
            return

        confirm = input("  Fix anwenden? [j/n]: ").strip().lower()
        if confirm != "j":
            print("\n  Abgebrochen.\n")
            return

        print("\n  Führe Fix durch...")
        apply_fix(conn, env, symbols, campaign_ids, args.prefix, logger)
        logger.info("Fix Symbol Mismatch abgeschlossen")
        print()
        print("  Fertig! Jetzt process_ibkr_trades erneut ausführen.")
        print(f"  Erwartetes Ergebnis: BMWd open -> BMW close via conid-Fallback.\n")


if __name__ == "__main__":
    main()
