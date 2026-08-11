"""
Scannt C:\\Trade_CSV\\incoming\\ nach neuen Activity-Statement-CSVs,
importiert jeden als account_snapshots-Eintrag und verschiebt die Datei
nach C:\\Trade_CSV\\incoming\\{user}\\processed\\.

Routing: accountId aus dem CSV-Inhalt → accounts.toml (via config.py::get_account_config())
         (funktioniert mit maskierten IDs wie U***1234)

Verwendung:
    python -m src.import_csv_snapshots
    python -m src.import_csv_snapshots --dry-run
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path
from sqlalchemy import text

from src.config import TABLE_ACCOUNT_SNAPSHOTS, get_account_config, get_engine
from src.logger_setup import setup_logging
from src.parsers.activity_csv_parser import ActivityCsvParser
from src.utils.path_utils import get_project_root

IN_FOLDER_CSV_INCOMING = Path(r'C:\Trade_CSV\incoming')

log_file = get_project_root() / "log/app.log"
logger, _ = setup_logging('my_app', level="simple", log_file=log_file)


def _insert_snapshot(snapshot: dict, environment: str, table_prefix: str, dry_run: bool) -> bool:
    """Schreibt Snapshot in account_snapshots. Gibt True zurück bei neuem Eintrag."""
    env_up = environment.upper()
    table  = f"{table_prefix}{TABLE_ACCOUNT_SNAPSHOTS}"
    engine = get_engine(environment)

    with engine.connect() as conn:
        existing = conn.execute(
            text(f"SELECT id FROM `{table}` WHERE snapshot_date = :d AND environment = :e"),
            {'d': snapshot['snapshot_date'], 'e': env_up}
        ).fetchone()

        if existing:
            logger.info(
                f"Snapshot {snapshot['snapshot_date']} [{env_up}] bereits vorhanden "
                f"(id={existing[0]}) — übersprungen"
            )
            return False

        if dry_run:
            logger.info(
                f"[DRY-RUN] Snapshot {snapshot['snapshot_date']} [{env_up}] "
                f"NAV: {snapshot['nav_current']} EUR | TWRR: {snapshot['twrr']}"
            )
            return True  # zählt als "würde importiert"

        row = {**snapshot, 'environment': env_up}
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
        """), row)
        conn.commit()

    logger.info(
        f"Snapshot {snapshot['snapshot_date']} [{env_up}] importiert — "
        f"NAV: {snapshot['nav_current']} EUR | TWRR: {snapshot['twrr']}"
    )
    return True


def _move_to_processed(csv_path: Path, user: str, dry_run: bool) -> None:
    """Verschiebt verarbeitete CSV nach incoming/{user}/processed/."""
    dest_dir  = IN_FOLDER_CSV_INCOMING / user / "processed"
    dest_path = dest_dir / csv_path.name
    if dry_run:
        logger.info(f"[DRY-RUN] Würde verschieben: {csv_path.name} → {dest_dir}")
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    if dest_path.exists():
        csv_path.unlink()
        logger.info(f"Duplikat in processed — gelöscht: {csv_path.name}")
    else:
        shutil.move(str(csv_path), str(dest_path))
        logger.info(f"Verschoben: {csv_path.name} → {dest_dir}")


def process_csv_file(csv_path: Path, dry_run: bool) -> bool:
    """
    Verarbeitet eine einzelne Activity-CSV.
    Gibt True zurück wenn ein neuer Snapshot importiert wurde.
    """
    try:
        parser = ActivityCsvParser(csv_path)
    except Exception as e:
        logger.error(f"{csv_path.name}: Parsing fehlgeschlagen — {e}")
        return False

    snapshot = parser.snapshot
    if not snapshot.get('snapshot_date'):
        logger.error(f"{csv_path.name}: Kein Datum im CSV — übersprungen")
        return False

    if not parser.account_id:
        logger.error(f"{csv_path.name}: Keine accountId im CSV — übersprungen")
        return False

    account_cfg = get_account_config(parser.account_id)
    if not account_cfg:
        logger.warning(
            f"{csv_path.name}: accountId '{parser.account_id}' "
            f"nicht in accounts.toml — übersprungen"
        )
        return False

    environment  = account_cfg['environment']
    table_prefix = account_cfg['table_prefix']
    user         = account_cfg['user']

    try:
        imported = _insert_snapshot(snapshot, environment, table_prefix, dry_run)
    except Exception as e:
        logger.error(f"{csv_path.name}: DB-Fehler — {e}")
        return False

    # CSV verschieben — auch bei Duplikat (Datei aus incoming räumen)
    _move_to_processed(csv_path, user, dry_run)
    return imported


def main() -> int:
    argp = argparse.ArgumentParser(description="Importiert account_snapshots aus Activity-Statement-CSVs")
    argp.add_argument('--dry-run', action='store_true', help='Nur anzeigen, nicht einfügen')
    args = argp.parse_args()

    logger.info("=" * 80)
    logger.info(f"---- Snapshot-Import CSV ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    logger.info("=" * 80)

    if not IN_FOLDER_CSV_INCOMING.exists():
        logger.error(f"Eingangsordner nicht gefunden: {IN_FOLDER_CSV_INCOMING}")
        return 0

    # Nur direkt im incoming-Ordner liegende CSVs (nicht in Unterordnern)
    csv_files = sorted(IN_FOLDER_CSV_INCOMING.glob('*.csv'))

    if not csv_files:
        logger.info("Keine neuen CSV-Dateien im Eingangsordner.")
        return 0

    logger.info(f"{len(csv_files)} CSV-Datei(en) gefunden")

    total = 0
    for csv_path in csv_files:
        logger.info(f"Verarbeite: {csv_path.name}")
        if process_csv_file(csv_path, dry_run=args.dry_run):
            total += 1

    mode = "[DRY-RUN] " if args.dry_run else ""
    logger.info(f"Fertig: {mode}{total} neue Snapshot(s) importiert")
    print(f"Fertig, Snapshots importiert: {total}")
    return total


if __name__ == '__main__':
    sys.exit(0 if main() >= 0 else 1)
