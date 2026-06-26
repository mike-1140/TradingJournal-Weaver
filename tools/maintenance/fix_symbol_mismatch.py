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
# Beispiel:
#   .venv\Scripts\python.exe tools/maintenance/fix_symbol_mismatch.py -e paper -s BMWd -a BMW

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))

import argparse
from sqlalchemy import text
import src.config as config
from src.config import get_engine, DB_MAP
from src.logger_setup import setup_logging
from src.utils.path_utils import get_project_root


def _prefixed(table: str) -> str:
    return f"{config.TABLE_PREFIX}{table}" if config.TABLE_PREFIX else table


def diagnose(conn, env: str, symbols: list[str]) -> dict:
    """Zeigt den aktuellen Zustand aller betroffenen Datensätze."""
    placeholders = ", ".join(f":s{i}" for i in range(len(symbols)))
    sym_params = {f"s{i}": s for i, s in enumerate(symbols)}

    result = {}

    # trades_raw
    t = _prefixed("trades_raw")
    sql = text(f"""
        SELECT id, symbol, buySell, quantity, dateTime, processed
        FROM {t}
        WHERE environment = :env
          AND (symbol IN ({placeholders}) OR underlyingSymbol IN ({placeholders}))
        ORDER BY dateTime
    """)
    result["trades_raw"] = conn.execute(sql, {"env": env, **sym_params}).fetchall()

    # trades_open
    t = _prefixed("trades_open")
    sql = text(f"""
        SELECT id, symbol, buySell, quantity, dateTime, processed
        FROM {t}
        WHERE environment = :env
          AND (symbol IN ({placeholders}) OR underlyingSymbol IN ({placeholders}))
        ORDER BY dateTime
    """)
    result["trades_open"] = conn.execute(sql, {"env": env, **sym_params}).fetchall()

    # trades_close
    t = _prefixed("trades_close")
    sql = text(f"""
        SELECT id, symbol, buySellOpen, buySellClose, quantity, dateTimeOpen, dateTimeClose
        FROM {t}
        WHERE environment = :env
          AND (symbol IN ({placeholders}) OR underlyingSymbol IN ({placeholders}))
        ORDER BY dateTimeOpen
    """)
    result["trades_close"] = conn.execute(sql, {"env": env, **sym_params}).fetchall()

    # trading_campaigns
    tc = _prefixed("trading_campaigns")
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
        cl = _prefixed("campaign_ledger")
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


def apply_fix(conn, env: str, symbols: list[str], campaign_ids: list[int]):
    """Führt den Reset durch — in der richtigen FK-Reihenfolge."""
    placeholders = ", ".join(f":s{i}" for i in range(len(symbols)))
    sym_params = {f"s{i}": s for i, s in enumerate(symbols)}

    # 1. campaign_ledger löschen
    if campaign_ids:
        ledger_placeholders = ", ".join(f":c{i}" for i in range(len(campaign_ids)))
        cl = _prefixed("campaign_ledger")
        sql = text(f"DELETE FROM {cl} WHERE campaign_id IN ({ledger_placeholders})")
        r = conn.execute(sql, {f"c{i}": cid for i, cid in enumerate(campaign_ids)})
        print(f"    campaign_ledger:    {r.rowcount:>5} Zeilen gelöscht")

    # 2. trading_campaigns auf PENDING zurücksetzen
    if campaign_ids:
        tc = _prefixed("trading_campaigns")
        ledger_placeholders = ", ".join(f":c{i}" for i in range(len(campaign_ids)))
        sql = text(f"""
            UPDATE {tc}
            SET status = 'ACTIVE', end_date = NULL, closed_at = NULL
            WHERE id IN ({ledger_placeholders})
        """)
        r = conn.execute(sql, {f"c{i}": cid for i, cid in enumerate(campaign_ids)})
        print(f"    trading_campaigns:  {r.rowcount:>5} auf PENDING gesetzt")

    # 3. trades_close löschen
    t = _prefixed("trades_close")
    sql = text(f"""
        DELETE FROM {t}
        WHERE environment = :env
          AND (symbol IN ({placeholders}) OR underlyingSymbol IN ({placeholders}))
    """)
    r = conn.execute(sql, {"env": env, **sym_params})
    print(f"    trades_close:       {r.rowcount:>5} Zeilen gelöscht")

    # 4. trades_open löschen
    t = _prefixed("trades_open")
    sql = text(f"""
        DELETE FROM {t}
        WHERE environment = :env
          AND (symbol IN ({placeholders}) OR underlyingSymbol IN ({placeholders}))
    """)
    r = conn.execute(sql, {"env": env, **sym_params})
    print(f"    trades_open:        {r.rowcount:>5} Zeilen gelöscht")

    # 5. trades_raw auf processed=0 zurücksetzen
    t = _prefixed("trades_raw")
    sql = text(f"""
        UPDATE {t}
        SET processed = 0
        WHERE environment = :env
          AND (symbol IN ({placeholders}) OR underlyingSymbol IN ({placeholders}))
    """)
    r = conn.execute(sql, {"env": env, **sym_params})
    print(f"    trades_raw:         {r.rowcount:>5} auf processed=0 gesetzt")

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
    parser.add_argument("--prefix", "-p", default=None,
                        help=f"Tabellen-Prefix überschreiben (default: aus .env = '{config.TABLE_PREFIX}')")
    args = parser.parse_args()

    if args.prefix is not None:
        config.TABLE_PREFIX = args.prefix

    symbols = [args.symbol.upper()]
    if args.alias:
        symbols.append(args.alias.upper())

    env = args.environment.upper()

    print()
    print("=" * 65)
    print("  FIX SYMBOL MISMATCH — Symbol-Reset")
    print("=" * 65)
    print(f"  Environment:  {env}")
    print(f"  Prefix:       '{config.TABLE_PREFIX}'")
    print(f"  Symbole:      {', '.join(symbols)}")
    print("=" * 65)

    engine = get_engine(args.environment)

    with engine.connect() as conn:
        data = diagnose(conn, env, symbols)

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

        confirm = input("  Fix anwenden? [j/n]: ").strip().lower()
        if confirm != "j":
            print("\n  Abgebrochen.\n")
            return

        print("\n  Führe Fix durch...")
        apply_fix(conn, env, symbols, campaign_ids)
        print()
        print("  Fertig! Jetzt process_ibkr_trades erneut ausführen.")
        print(f"  Erwartetes Ergebnis: BMWd open -> BMW close via conid-Fallback.\n")


if __name__ == "__main__":
    main()
