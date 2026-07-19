# tools/maintenance/cleanup_stale_positions.py
"""
Entfernt "liegen gebliebene" offene Positionen (Altlasten) rückstandsfrei.

Szenario: Die Eröffnung wurde importiert, das Schließen aber nie — die Position
existiert im echten Konto längst nicht mehr, steht aber weiterhin in trades_open
und hält die zugehörige Kampagne auf ACTIVE.

Betroffene Tabellen:
  - trades_open        (die liegengebliebene FIFO-Tranche)
  - campaign_ledger    (Open-Buchung via source_table='TRADES_OPEN' + source_id)
  - trades_raw         (Original-Importzeile, via checksum bzw. tradeID)
  - trading_campaigns  (Kampagne löschen wenn danach leer, sonst Status +
                        Running-Balance (cum_*) neu berechnen)

Aufruf (Dry-Run ist Standard, es wird NICHTS gelöscht):
  python tools/maintenance/cleanup_stale_positions.py paper                     # alle offenen Positionen anzeigen
  python tools/maintenance/cleanup_stale_positions.py paper --ids 12,34         # Vorschau für Auswahl
  python tools/maintenance/cleanup_stale_positions.py paper --symbols ABC,XYZ   # Auswahl per Symbol
  python tools/maintenance/cleanup_stale_positions.py paper --older-than 2026-01-01
  python tools/maintenance/cleanup_stale_positions.py paper --ids 12,34 --execute

Optionen:
  --prefix mike_    Table-Prefix (Standard: TABLE_PREFIX aus .env)
  --all             alle offenen Positionen des Environments auswählen
  --execute         tatsächlich löschen (mit Sicherheitsabfrage)
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parents[2]))  # xml_proj/ in sys.path

from sqlalchemy import text

from src.config import (
    get_engine, DB_MAP, TABLE_PREFIX,
    TABLE_TRADES_RAW, TABLE_TRADES_OPEN,
    TABLE_CAMPAIGN_LEDGER, TABLE_TRADING_CAMPAIGNS,
)
from src.logger_setup import setup_logging
from src.utils.path_utils import get_project_root


def _prefixed(prefix: str, table: str) -> str:
    return f"{prefix}{table}" if prefix else table


def find_stale_open_trades(conn, t_open: str, env_up: str, args) -> list[dict]:
    """
    Liest die ausgewählten offenen Tranchen aus trades_open.
    Wichtig: processed = 0 — geschlossene Tranchen werden nicht gelöscht,
    sondern nur auf processed = 1 gesetzt (History). Nur processed = 0 ist
    tatsächlich noch offen (so filtert auch TradingJournal2).
    """
    conditions = ["environment = :env", "processed = 0"]
    params: dict = {"env": env_up}

    if args.ids:
        id_list = [int(x) for x in args.ids.split(",")]
        placeholders = ", ".join(f":id{i}" for i in range(len(id_list)))
        conditions.append(f"id IN ({placeholders})")
        params.update({f"id{i}": v for i, v in enumerate(id_list)})
    if args.symbols:
        sym_list = [s.strip().upper() for s in args.symbols.split(",")]
        placeholders = ", ".join(f":sym{i}" for i in range(len(sym_list)))
        conditions.append(f"UPPER(symbol) IN ({placeholders})")
        params.update({f"sym{i}": v for i, v in enumerate(sym_list)})
    if args.older_than:
        conditions.append("dateTime < :older_than")
        params["older_than"] = args.older_than

    sql = text(f"""
        SELECT id, symbol, assetCategory, quantity, dateTime, status,
               tradeID, checksum
        FROM `{t_open}`
        WHERE {' AND '.join(conditions)}
        ORDER BY dateTime, id
    """)
    return [dict(row._mapping) for row in conn.execute(sql, params)]


def collect_related_rows(conn, tables: dict, env_up: str, open_trades: list[dict]) -> dict:
    """Sammelt zu jeder Tranche die Ledger- und Raw-Zeilen sowie die Kampagnen-IDs."""
    ledger_ids: list[int] = []
    raw_ids: list[int] = []
    campaign_ids: set[int] = set()
    per_trade: dict[int, dict] = {}

    for ot in open_trades:
        # Ledger-Buchungen, die direkt auf diese trades_open-Zeile zeigen
        rows = conn.execute(text(f"""
            SELECT id, campaign_id, action
            FROM `{tables['ledger']}`
            WHERE environment = :env
              AND source_table = 'TRADES_OPEN'
              AND source_id = :sid
        """), {"env": env_up, "sid": ot["id"]}).fetchall()
        trade_ledger_ids = [r.id for r in rows]
        trade_campaigns = {r.campaign_id for r in rows}

        # Original-Importzeile: primär über checksum, sonst über tradeID
        raw_rows = []
        if ot["checksum"]:
            raw_rows = conn.execute(text(f"""
                SELECT id FROM `{tables['raw']}`
                WHERE environment = :env AND checksum = :cs
            """), {"env": env_up, "cs": ot["checksum"]}).fetchall()
        if not raw_rows and ot["tradeID"]:
            raw_rows = conn.execute(text(f"""
                SELECT id FROM `{tables['raw']}`
                WHERE environment = :env AND tradeID = :tid
            """), {"env": env_up, "tid": ot["tradeID"]}).fetchall()
        trade_raw_ids = [r.id for r in raw_rows]

        ledger_ids.extend(trade_ledger_ids)
        raw_ids.extend(trade_raw_ids)
        campaign_ids.update(trade_campaigns)
        per_trade[ot["id"]] = {
            "ledger_ids": trade_ledger_ids,
            "raw_ids": trade_raw_ids,
            "campaign_ids": trade_campaigns,
        }

    return {
        "ledger_ids": ledger_ids,
        "raw_ids": raw_ids,
        "campaign_ids": campaign_ids,
        "per_trade": per_trade,
    }


def print_preview(open_trades: list[dict], related: dict) -> None:
    """Zeigt an, was gelöscht werden würde."""
    print(f"\n{'ID':>6}  {'Symbol':<28} {'Typ':<5} {'Menge':>10}  {'Datum':<19} "
          f"{'Status':<10} {'Ledger':>6} {'Raw':>4}  Kampagne(n)")
    print("-" * 110)
    for ot in open_trades:
        info = related["per_trade"][ot["id"]]
        campaigns = ", ".join(str(c) for c in sorted(info["campaign_ids"])) or "-"
        dt = ot["dateTime"].strftime("%Y-%m-%d %H:%M:%S") if ot["dateTime"] else "-"
        print(f"{ot['id']:>6}  {ot['symbol']:<28} {ot['assetCategory'] or '-':<5} "
              f"{ot['quantity']:>10}  {dt:<19} {ot['status'] or '-':<10} "
              f"{len(info['ledger_ids']):>6} {len(info['raw_ids']):>4}  {campaigns}")
    print("-" * 110)
    print(f"Summe: {len(open_trades)} Tranche(n), {len(related['ledger_ids'])} Ledger-Zeile(n), "
          f"{len(related['raw_ids'])} Raw-Zeile(n), {len(related['campaign_ids'])} betroffene Kampagne(n)\n")


def _delete_by_ids(conn, table: str, ids: list[int]) -> int:
    """Löscht Zeilen einer Tabelle per ID-Liste, gibt Anzahl zurück."""
    if not ids:
        return 0
    placeholders = ", ".join(f":id{i}" for i in range(len(ids)))
    result = conn.execute(
        text(f"DELETE FROM `{table}` WHERE id IN ({placeholders})"),
        {f"id{i}": v for i, v in enumerate(ids)},
    )
    return result.rowcount


def _recalc_running_balance(conn, t_ledger: str, campaign_id: int) -> None:
    """Berechnet cum_pnl / cum_commission / cum_premium einer Kampagne komplett neu."""
    conn.execute(text(f"""
        UPDATE `{t_ledger}` cl
        JOIN (
            SELECT id,
                SUM(realized_pnl) OVER w AS new_cum_pnl,
                SUM(commission)   OVER w AS new_cum_commission,
                SUM(proceeds)     OVER w AS new_cum_premium
            FROM `{t_ledger}`
            WHERE campaign_id = :cid
            WINDOW w AS (ORDER BY dateTime, id
                         ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        ) calc ON cl.id = calc.id
        SET cl.cum_pnl        = calc.new_cum_pnl,
            cl.cum_commission = calc.new_cum_commission,
            cl.cum_premium    = calc.new_cum_premium
        WHERE cl.campaign_id = :cid
    """), {"cid": campaign_id})


def cleanup_campaign(conn, tables: dict, campaign_id: int, logger) -> None:
    """
    Räumt eine betroffene Kampagne auf:
      - keine Ledger-Zeilen mehr  → Kampagne löschen
      - Restbestand = 0           → Status CLOSED, closed_at/end_date = letztes Event
      - Restbestand != 0          → Kampagne bleibt wie sie ist (nur Running-Balance neu)
    """
    row = conn.execute(text(f"""
        SELECT COUNT(*) AS cnt,
               COALESCE(SUM(inventory_delta), 0) AS inventory,
               MAX(dateTime) AS last_event
        FROM `{tables['ledger']}`
        WHERE campaign_id = :cid
    """), {"cid": campaign_id}).one()

    if row.cnt == 0:
        conn.execute(text(f"DELETE FROM `{tables['campaigns']}` WHERE id = :cid"),
                     {"cid": campaign_id})
        logger.info(f"  Kampagne {campaign_id}: keine Buchungen mehr -> geloescht")
        return

    _recalc_running_balance(conn, tables["ledger"], campaign_id)

    if row.inventory == 0:
        conn.execute(text(f"""
            UPDATE `{tables['campaigns']}`
            SET status = 'CLOSED', end_date = :dt, closed_at = :dt
            WHERE id = :cid AND status != 'CLOSED'
        """), {"cid": campaign_id, "dt": row.last_event})
        logger.info(f"  Kampagne {campaign_id}: Restbestand 0 -> Status CLOSED, "
                    f"Running-Balance neu berechnet ({row.cnt} Buchungen)")
    else:
        logger.info(f"  Kampagne {campaign_id}: Restbestand {row.inventory} -> bleibt offen, "
                    f"Running-Balance neu berechnet ({row.cnt} Buchungen)")


def main():
    parser = argparse.ArgumentParser(
        description="Entfernt liegengebliebene offene Positionen rückstandsfrei aus allen Tabellen.")
    parser.add_argument("environment", choices=list(DB_MAP.keys()))
    parser.add_argument("--prefix", default=TABLE_PREFIX,
                        help="Table-Prefix, z.B. mike_ (Standard: TABLE_PREFIX aus .env)")
    parser.add_argument("--ids", help="Kommagetrennte trades_open-IDs, z.B. 12,34")
    parser.add_argument("--symbols", help="Kommagetrennte Symbole, z.B. ABC,XYZ")
    parser.add_argument("--older-than", help="Nur Tranchen vor diesem Datum (YYYY-MM-DD)")
    parser.add_argument("--all", action="store_true",
                        help="Alle offenen Positionen des Environments auswählen")
    parser.add_argument("--execute", action="store_true",
                        help="Tatsächlich löschen (Standard: Dry-Run)")
    args = parser.parse_args()

    env = args.environment.lower()
    env_up = env.upper()

    has_selection = bool(args.ids or args.symbols or args.older_than or args.all)

    tables = {
        "open":      _prefixed(args.prefix, TABLE_TRADES_OPEN),
        "raw":       _prefixed(args.prefix, TABLE_TRADES_RAW),
        "ledger":    _prefixed(args.prefix, TABLE_CAMPAIGN_LEDGER),
        "campaigns": _prefixed(args.prefix, TABLE_TRADING_CAMPAIGNS),
    }

    log_file = get_project_root() / "log/app.log"
    logger, _ = setup_logging("cleanup_stale", level="simple", log_file=log_file)
    logger.info("=" * 80)
    logger.info(f"---- Cleanup liegengebliebener Positionen "
                f"({datetime.now().strftime('%Y-%m-%d - %H:%M:%S')})")
    logger.info(f"Environment: {env_up}, Präfix: '{args.prefix}', "
                f"Modus: {'EXECUTE' if args.execute else 'DRY-RUN'}")

    engine = get_engine(env)
    with engine.connect() as conn:
        open_trades = find_stale_open_trades(conn, tables["open"], env_up, args)
        if not open_trades:
            print(f"\nKeine passenden offenen Positionen in {env_up} gefunden.")
            return

        related = collect_related_rows(conn, tables, env_up, open_trades)
        print_preview(open_trades, related)

    if not has_selection:
        print("Das ist die vollständige Liste der offenen Positionen (nur Anzeige).")
        print("Auswahl treffen mit --ids, --symbols, --older-than oder --all,")
        print("dann mit --execute tatsächlich löschen.")
        return

    if not args.execute:
        print("DRY-RUN: Es wurde nichts gelöscht. Zum Ausführen --execute anhängen.")
        return

    # Sicherheitsabfrage vor dem tatsächlichen Löschen
    answer = input(f"{len(open_trades)} Tranche(n) inkl. Ledger/Raw aus {env_up} "
                   f"(Prefix '{args.prefix}') endgültig löschen? (ja/nein): ")
    if answer.strip().lower() != "ja":
        print("Abgebrochen, es wurde nichts gelöscht.")
        return

    with engine.begin() as conn:
        n_ledger = _delete_by_ids(conn, tables["ledger"], related["ledger_ids"])
        n_open = _delete_by_ids(conn, tables["open"], [ot["id"] for ot in open_trades])
        n_raw = _delete_by_ids(conn, tables["raw"], related["raw_ids"])
        logger.info(f"Gelöscht: {n_open} trades_open, {n_ledger} campaign_ledger, "
                    f"{n_raw} trades_raw")

        for cid in sorted(related["campaign_ids"]):
            cleanup_campaign(conn, tables, cid, logger)

    logger.info("Cleanup abgeschlossen")
    print("\nCleanup abgeschlossen — Details siehe log/app.log")


if __name__ == "__main__":
    main()
