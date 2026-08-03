# tools/maintenance/purge_stale_trades.py
#
# Interaktives Tool zum Bereinigen von "Trade-Leichen" —
# alte offene Positionen die bei IBKR nicht mehr existieren
# (z.B. Paper-Account: max. 6 Monate History)
#
# Aufruf (Dry-Run ist Standard, es wird NICHTS gelöscht):
#   .venv\Scripts\python.exe tools/maintenance/purge_stale_trades.py -e paper
#   .venv\Scripts\python.exe tools/maintenance/purge_stale_trades.py -e paper --execute

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))

import argparse
from datetime import datetime, timedelta
from sqlalchemy import text
import src.config as config
from src.config import (
    get_engine, DB_MAP,
    TABLE_TRADES_RAW, TABLE_TRADES_OPEN, TABLE_TRADES_CLOSE,
    TABLE_CAMPAIGN_LEDGER, TABLE_TRADING_CAMPAIGNS,
)
from src.logger_setup import setup_logging
from src.utils.path_utils import get_project_root


def _prefixed(prefix: str, table: str) -> str:
    return f"{prefix}{table}" if prefix else table


def get_stale_open_trades(conn, environment: str, cutoff_date: datetime, prefix: str):
    """Alle offenen Trades die älter als cutoff_date sind"""
    table = _prefixed(prefix, TABLE_TRADES_OPEN)
    sql = text(f"""
        SELECT id, symbol, underlyingSymbol, assetCategory, dateTime,
               quantity, netCash, tradePrice, tradeID, status, opt_strategyID,
               description, putCall, strike, expiry
        FROM {table}
        WHERE environment = :env
          AND dateTime < :cutoff
        ORDER BY symbol, dateTime
    """)
    return conn.execute(sql, {"env": environment, "cutoff": cutoff_date}).fetchall()


def count_related_records(conn, environment: str, symbols: list[str], prefix: str):
    """Zähle betroffene Datensätze in allen Tabellen für die gegebenen Symbole"""
    counts = {}

    for counts_key, table_const, symbol_col in [
        ("trades_open", TABLE_TRADES_OPEN, "symbol"),
        ("trades_close", TABLE_TRADES_CLOSE, "symbol"),
        ("trades_raw", TABLE_TRADES_RAW, "symbol"),
    ]:
        table = _prefixed(prefix, table_const)
        # IN-Klausel braucht expandiertes SQL
        placeholders = ", ".join(f":s{i}" for i in range(len(symbols)))
        sql = text(f"""
            SELECT COUNT(*) FROM {table}
            WHERE environment = :env
              AND ({symbol_col} IN ({placeholders}) OR underlyingSymbol IN ({placeholders}))
        """)
        params = {"env": environment}
        for i, s in enumerate(symbols):
            params[f"s{i}"] = s
        result = conn.execute(sql, params).scalar()
        counts[counts_key] = result

    # campaign_ledger + trading_campaigns: über Symbol
    campaign_table = _prefixed(prefix, TABLE_TRADING_CAMPAIGNS)
    ledger_table = _prefixed(prefix, TABLE_CAMPAIGN_LEDGER)

    placeholders = ", ".join(f":s{i}" for i in range(len(symbols)))
    params = {"env": environment}
    for i, s in enumerate(symbols):
        params[f"s{i}"] = s

    sql = text(f"""
        SELECT COUNT(*) FROM {campaign_table}
        WHERE environment = :env AND symbol IN ({placeholders})
    """)
    counts["trading_campaigns"] = conn.execute(sql, params).scalar()

    sql = text(f"""
        SELECT COUNT(*) FROM {ledger_table} l
        JOIN {campaign_table} c ON l.campaign_id = c.id
        WHERE c.environment = :env AND c.symbol IN ({placeholders})
    """)
    counts["campaign_ledger"] = conn.execute(sql, params).scalar()

    return counts


def purge_symbol_data(conn, environment: str, symbols: list[str], prefix: str, logger):
    """Lösche alle Daten für die gegebenen Symbole aus allen Tabellen"""
    placeholders = ", ".join(f":s{i}" for i in range(len(symbols)))
    params = {"env": environment}
    for i, s in enumerate(symbols):
        params[f"s{i}"] = s

    campaign_table = _prefixed(prefix, TABLE_TRADING_CAMPAIGNS)
    ledger_table = _prefixed(prefix, TABLE_CAMPAIGN_LEDGER)

    # 1. campaign_ledger zuerst (FK auf trading_campaigns)
    sql = text(f"""
        DELETE l FROM {ledger_table} l
        JOIN {campaign_table} c ON l.campaign_id = c.id
        WHERE c.environment = :env AND c.symbol IN ({placeholders})
    """)
    result = conn.execute(sql, params)
    logger.info(f"  campaign_ledger: {result.rowcount} Zeilen gelöscht")

    # 2. trading_campaigns
    sql = text(f"""
        DELETE FROM {campaign_table}
        WHERE environment = :env AND symbol IN ({placeholders})
    """)
    result = conn.execute(sql, params)
    logger.info(f"  trading_campaigns: {result.rowcount} Zeilen gelöscht")

    # 3. trades_close
    table = _prefixed(prefix, TABLE_TRADES_CLOSE)
    sql = text(f"""
        DELETE FROM {table}
        WHERE environment = :env
          AND (symbol IN ({placeholders}) OR underlyingSymbol IN ({placeholders}))
    """)
    result = conn.execute(sql, params)
    logger.info(f"  trades_close: {result.rowcount} Zeilen gelöscht")

    # 4. trades_open
    table = _prefixed(prefix, TABLE_TRADES_OPEN)
    sql = text(f"""
        DELETE FROM {table}
        WHERE environment = :env
          AND (symbol IN ({placeholders}) OR underlyingSymbol IN ({placeholders}))
    """)
    result = conn.execute(sql, params)
    logger.info(f"  trades_open: {result.rowcount} Zeilen gelöscht")

    # 5. trades_raw
    table = _prefixed(prefix, TABLE_TRADES_RAW)
    sql = text(f"""
        DELETE FROM {table}
        WHERE environment = :env
          AND (symbol IN ({placeholders}) OR underlyingSymbol IN ({placeholders}))
    """)
    result = conn.execute(sql, params)
    logger.info(f"  trades_raw: {result.rowcount} Zeilen gelöscht")

    conn.commit()


def format_trade_row(idx: int, trade) -> str:
    """Formatiere eine Trade-Zeile für die Anzeige"""
    symbol = trade.symbol or "?"
    asset = trade.assetCategory or "?"
    dt = trade.dateTime.strftime("%Y-%m-%d") if trade.dateTime else "?"
    qty = f"{float(trade.quantity):>8.1f}" if trade.quantity else "       ?"
    net = f"{float(trade.netCash):>10.2f}" if trade.netCash else "         ?"

    extra = ""
    if asset in ("OPT", "FOP") and trade.putCall and trade.strike:
        extra = f"  ({trade.putCall} {float(trade.strike):.0f})"
        if trade.expiry:
            extra += f" exp {trade.expiry.strftime('%Y-%m-%d')}"

    return f"  {idx:>3}  {symbol:<25} {asset:<5} {dt}  {qty}  {net}{extra}"


def main():
    parser = argparse.ArgumentParser(
        description="Bereinigung alter Trade-Leichen aus dem Trading-Journal"
    )
    parser.add_argument(
        "--environment", "-e",
        default="paper",
        choices=list(DB_MAP.keys()),
        help="Trading-Environment (default: paper)"
    )
    parser.add_argument(
        "--months", "-m",
        type=int,
        default=6,
        help="Trades älter als X Monate anzeigen (default: 6)"
    )
    parser.add_argument(
        "--prefix", "-p",
        default=config.TABLE_PREFIX,
        help=f"Table Prefix überschreiben (default: aus .env = '{config.TABLE_PREFIX}')"
    )
    parser.add_argument("--execute", action="store_true",
                        help="Tatsächlich löschen (Standard: Dry-Run)")
    args = parser.parse_args()

    # Logging
    log_file = get_project_root() / "log/app.log"
    logger, _ = setup_logging("purge_stale", level="simple", log_file=log_file)

    environment = args.environment.upper()
    cutoff_date = datetime.now() - timedelta(days=args.months * 30)

    logger.info("=" * 80)
    logger.info(f"---- Purge Stale Trades ({environment}, Präfix: '{args.prefix}', "
                f"Modus: {'EXECUTE' if args.execute else 'DRY-RUN'})")

    print()
    print("=" * 70)
    print("  PURGE STALE TRADES — Bereinigung alter Trade-Leichen")
    print("=" * 70)
    print(f"  Environment:  {environment}")
    print(f"  Prefix:       '{args.prefix}' ")
    print(f"  Cutoff:       {args.months} Monate -> älter als {cutoff_date.strftime('%Y-%m-%d')}")
    print("=" * 70)

    engine = get_engine(args.environment)

    with engine.connect() as conn:
        # Stale Trades laden
        stale_trades = get_stale_open_trades(conn, environment, cutoff_date, args.prefix)

        if not stale_trades:
            print("\n  Keine offenen Trades älter als der Cutoff gefunden.")
            print("  Nichts zu tun.\n")
            return

        # Nach underlyingSymbol gruppieren für die Anzeige
        symbols_seen = {}
        for trade in stale_trades:
            underlying = trade.underlyingSymbol or trade.symbol
            if underlying not in symbols_seen:
                symbols_seen[underlying] = []
            symbols_seen[underlying].append(trade)

        print(f"\n  {len(stale_trades)} offene Trades in {len(symbols_seen)} Symbolen gefunden:\n")
        print(f"  {'#':>3}  {'Symbol':<25} {'Asset':<5} {'Datum'}      {'Qty':>8}  {'NetCash':>10}")
        print("  " + "-" * 80)

        for idx, trade in enumerate(stale_trades, 1):
            print(format_trade_row(idx, trade))

        # Interaktive Auswahl
        print()
        print("  Optionen:")
        print("    [a] Alle Symbole löschen")
        print("    [s] Nach Symbol auswählen")
        print("    [q] Abbrechen")
        print()

        choice = input("  Auswahl: ").strip().lower()

        if choice == "q":
            print("\n  Abgebrochen.\n")
            return

        if choice == "a":
            selected_symbols = list(symbols_seen.keys())
        elif choice == "s":
            print(f"\n  Verfügbare Symbole: {', '.join(sorted(symbols_seen.keys()))}")
            symbol_input = input("  Symbol(e) eingeben (kommagetrennt): ").strip().upper()
            selected_symbols = [s.strip() for s in symbol_input.split(",") if s.strip()]
            # Validieren
            invalid = [s for s in selected_symbols if s not in symbols_seen]
            if invalid:
                print(f"\n  Unbekannte Symbole: {', '.join(invalid)}")
                print("  Abgebrochen.\n")
                return
        else:
            print(f"\n  Ungültige Auswahl: '{choice}'")
            return

        if not selected_symbols:
            print("\n  Keine Symbole ausgewählt. Abgebrochen.\n")
            return

        # Betroffene Datensätze zählen
        print(f"\n  Zähle betroffene Datensätze für: {', '.join(selected_symbols)}...")
        counts = count_related_records(conn, environment, selected_symbols, args.prefix)

        print()
        print("  Zu löschende Datensätze:")
        print(f"    trades_open:        {counts['trades_open']:>6}")
        print(f"    trades_close:       {counts['trades_close']:>6}")
        print(f"    trades_raw:         {counts['trades_raw']:>6}")
        print(f"    campaign_ledger:    {counts['campaign_ledger']:>6}")
        print(f"    trading_campaigns:  {counts['trading_campaigns']:>6}")
        total = sum(counts.values())
        print(f"    {'-'*20}  ------")
        print(f"    GESAMT:             {total:>6}")
        print()

        if total == 0:
            print("  Keine Datensätze zu löschen.\n")
            return

        if not args.execute:
            print("  DRY-RUN: Es wurde nichts gelöscht. Zum Ausführen --execute anhängen.\n")
            return

        confirm = input("  Wirklich UNWIDERRUFLICH löschen? [j/n]: ").strip().lower()
        if confirm != "j":
            print("\n  Abgebrochen.\n")
            return

        # Löschen
        logger.info(f"Purge stale trades: {environment}, Symbole: {selected_symbols}")
        print(f"\n  Lösche Daten...")
        purge_symbol_data(conn, environment, selected_symbols, args.prefix, logger)

        print()
        print(f"  Fertig! {total} Datensätze gelöscht für: {', '.join(selected_symbols)}")
        print(f"  Details im Log: {log_file}\n")


if __name__ == "__main__":
    main()
