"""
Importiert einen IBKR Activity Statement CSV als täglichen account_snapshots-Eintrag.

Verwendung:
    python src/import_activity_statement.py <csv_pfad> <environment> [table_prefix]

Beispiel:
    python src/import_activity_statement.py U23465466_20260513.csv money mike_

Hinweis: Tabelle account_snapshots muss einmalig angelegt werden:
    mysql -u user -p ibkr_money < sql/account_snapshots.sql
"""

import sys
from datetime import datetime
from pathlib import Path
from sqlalchemy import text

from src.config import TABLE_PREFIX, TABLE_ACCOUNT_SNAPSHOTS, get_engine
from src.db.db_access import DBAccess
from src.logger_setup import setup_logging
from src.parsers.activity_csv_parser import ActivityCsvParser
from src.utils.path_utils import get_project_root

log_file = get_project_root() / "log/app.log"
logger, _ = setup_logging('my_app', level="simple", log_file=log_file)


def import_activity_statement(csv_path: str, environment: str, table_prefix: str) -> bool:
    """
    Parst CSV und schreibt Snapshot in account_snapshots.
    Gibt True zurück wenn ein neuer Eintrag geschrieben wurde, False bei Duplikat.
    """
    env_up = environment.upper()

    logger.info("=" * 80)
    logger.info(
        f"Activity Statement Import: {Path(csv_path).name} "
        f"[{env_up}] ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
    )
    logger.info("=" * 80)

    if not Path(csv_path).exists():
        logger.error(f"CSV-Datei nicht gefunden: {csv_path}")
        print(f"Fehler: Datei nicht gefunden: {csv_path}")
        return False

    parser = ActivityCsvParser(csv_path)
    snapshot = parser.snapshot

    if not snapshot.get('snapshot_date'):
        logger.error("Kein gültiges Datum im CSV gefunden — Abbruch")
        print("Fehler: Kein Datum im CSV gefunden.")
        return False

    db = DBAccess(logger, environment, table_prefix)
    table = db._prefixed(TABLE_ACCOUNT_SNAPSHOTS)

    with db.engine.connect() as conn:
        existing = conn.execute(
            text(f"SELECT id FROM `{table}` WHERE snapshot_date = :d AND environment = :e"),
            {'d': snapshot['snapshot_date'], 'e': env_up}
        ).fetchone()

        if existing:
            logger.info(
                f"Snapshot {snapshot['snapshot_date']} [{env_up}] bereits vorhanden (id={existing[0]}) - uebersprungen"
            )
            print(f"Snapshot {snapshot['snapshot_date']} [{env_up}] bereits in DB - uebersprungen.")
            return False

        conn.execute(text(f"""
            INSERT INTO `{table}` (
                snapshot_date, environment,
                nav_prior, nav_current, nav_change, twrr,
                starting_value, mtm_pnl, commissions_eur, ending_value,
                cash_eur, cash_usd, forex_translation_pnl,
                realized_pnl_eur, unrealized_pnl_eur,
                mtd_pnl, ytd_pnl,
                imported_at
            ) VALUES (
                :snapshot_date, :environment,
                :nav_prior, :nav_current, :nav_change, :twrr,
                :starting_value, :mtm_pnl, :commissions_eur, :ending_value,
                :cash_eur, :cash_usd, :forex_translation_pnl,
                :realized_pnl_eur, :unrealized_pnl_eur,
                :mtd_pnl, :ytd_pnl,
                :imported_at
            )
        """), {**snapshot, 'environment': env_up})
        conn.commit()

    logger.info(
        f"Snapshot {snapshot['snapshot_date']} [{env_up}] importiert — "
        f"NAV: {snapshot['nav_current']} EUR"
    )
    print(f"OK: Snapshot {snapshot['snapshot_date']} [{env_up}] importiert")
    _print_summary(snapshot)
    return True


def _print_summary(s: dict) -> None:
    def fmt(val) -> str:
        return str(val) if val is not None else 'N/A'

    def fmt_signed(val) -> str:
        if val is None:
            return 'N/A'
        return f"+{val}" if val >= 0 else str(val)

    print(f"  NAV aktuell:    {fmt(s['nav_current'])} EUR")
    print(f"  NAV Änderung:   {fmt_signed(s['nav_change'])} EUR")
    print(f"  TWRR:           {fmt(s['twrr'])}%")
    print(f"  Cash EUR:       {fmt(s['cash_eur'])}")
    print(f"  Cash USD:       {fmt(s['cash_usd'])}")
    print(f"  MTM P&L:        {fmt_signed(s['mtm_pnl'])}")
    print(f"  Realisiert:     {fmt_signed(s['realized_pnl_eur'])}")
    print(f"  Unrealisiert:   {fmt_signed(s['unrealized_pnl_eur'])}")
    print(f"  MTD P&L:        {fmt_signed(s['mtd_pnl'])}")
    print(f"  YTD P&L:        {fmt_signed(s['ytd_pnl'])}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage:   python src/import_activity_statement.py <csv_pfad> <environment> [table_prefix]")
        print("Beispiel: python src/import_activity_statement.py U23465466_20260513.csv money mike_")
        print("Environments: money | paper | test | autom_money | autom_paper")
        sys.exit(1)

    csv_path_arg = sys.argv[1]
    env_arg      = sys.argv[2].lower()
    prefix_arg   = sys.argv[3] if len(sys.argv) >= 4 else TABLE_PREFIX

    import_activity_statement(csv_path_arg, env_arg, prefix_arg)
