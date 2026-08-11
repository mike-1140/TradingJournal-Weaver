"""
Importiert account_snapshots aus IBKR FlexQuery Activity XMLs (per API-Abruf durch
get_flexquery_api.py nach C:\\Trade_XML\\incoming_api\\ geschrieben).

Ablauf:
  1. Alle XMLs in IN_FOLDER_XML_INCOMING_API scannen (oder einzelne Datei via --file)
  2. Pro XML: alle FlexStatements parsen (ein Statement = ein Snapshot-Tag)
  3. accountId → Environment/User/Prefix via accounts.toml (config.py::get_account_config()) auflösen
  4. Snapshot in account_snapshots einfügen (Duplikate überspringen)

Verschiebt/loescht die XML-Datei NICHT — das uebernimmt der nachfolgende import-Schritt
(import_ibkr_trades.py), der incoming_api/ zusaetzlich zu incoming_mail/ fuer trades_raw
scannt und als einziger Schritt fuer processed/deleted zustaendig ist. In pipeline.toml
laeuft snapshot_import bewusst VOR import, damit die Datei beim Scan noch vorhanden ist.

Verwendung:
    python src/import_flexquery_snapshot.py
    python src/import_flexquery_snapshot.py --dry-run
    python src/import_flexquery_snapshot.py --file C:\\Trade_XML\\incoming_api\\U12109360_20260525_act_money_per_api_0870.xml
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from sqlalchemy import text

from src.config import TABLE_ACCOUNT_SNAPSHOTS, get_account_config, get_engine
from src.logger_setup import setup_logging
from src.parsers.flexquery_snapshot_parser import FlexquerySnapshotParser
from src.utils.path_utils import get_project_root

IN_FOLDER_XML_INCOMING_API = Path(r'C:\Trade_XML\incoming_api')

log_file = get_project_root() / "log/app.log"
logger, _ = setup_logging('my_app', level="simple", log_file=log_file)


def _insert_snapshot(snapshot: dict, environment: str, table_prefix: str, dry_run: bool) -> bool:
    """
    Schreibt einen Snapshot in account_snapshots.
    Gibt True zurück wenn ein neuer Eintrag geschrieben wurde, False bei Duplikat oder Dry-Run.
    """
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
            return False

        row = {k: v for k, v in snapshot.items() if k != 'account_id'}
        row['environment'] = env_up

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


def process_xml_file(xml_path: Path, dry_run: bool) -> int:
    """Verarbeitet eine XML-Datei. Gibt Anzahl neu importierter Snapshots zurück."""
    try:
        content = xml_path.read_text(encoding='utf-8')
    except Exception as e:
        logger.error(f"{xml_path.name}: Lesen fehlgeschlagen — {e}")
        return 0

    try:
        parser = FlexquerySnapshotParser(content)
    except Exception as e:
        logger.error(f"{xml_path.name}: XML-Parsing fehlgeschlagen — {e}")
        return 0

    if not parser.snapshots:
        logger.info(f"{xml_path.name}: Keine Snapshots gefunden — übersprungen")
        return 0

    logger.info(f"{xml_path.name}: {len(parser.snapshots)} Snapshot(s) gefunden")

    cnt = 0
    for snap in parser.snapshots:
        account_cfg = get_account_config(snap['account_id'])
        if not account_cfg:
            logger.warning(
                f"{xml_path.name}: accountId '{snap['account_id']}' "
                f"nicht in accounts.toml — übersprungen"
            )
            continue
        try:
            if _insert_snapshot(snap, account_cfg['environment'], account_cfg['table_prefix'], dry_run):
                cnt += 1
        except Exception as e:
            logger.error(
                f"{xml_path.name}: Snapshot {snap['snapshot_date']} Fehler — {e}"
            )

    return cnt


def _print_summary(snapshots: list[dict], dry_run: bool) -> None:
    def fmt(val) -> str:
        return f"{val:+.2f}" if val is not None else 'N/A'

    mode = " [DRY-RUN]" if dry_run else ""
    for s in snapshots:
        print(f"  {s['snapshot_date']}{mode}  NAV: {s['nav_current']} EUR  "
              f"Δ {fmt(s['nav_change'])}  TWRR: {fmt(s['twrr'])}%  "
              f"Realisiert: {fmt(s['realized_pnl_eur'])}")


def main() -> int:
    argp = argparse.ArgumentParser(description="Importiert account_snapshots aus FlexQuery XMLs")
    argp.add_argument('--file',    metavar='XML', help='Einzelne XML-Datei statt Ordner-Scan')
    argp.add_argument('--dry-run', action='store_true', help='Nur anzeigen, nicht einfügen')
    args = argp.parse_args()

    logger.info("=" * 80)
    logger.info(f"---- Snapshot-Import XML ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    logger.info("=" * 80)

    if args.file:
        xml_files = [Path(args.file)]
        if not xml_files[0].exists():
            logger.error(f"Datei nicht gefunden: {args.file}")
            return 1
    else:
        if not IN_FOLDER_XML_INCOMING_API.exists():
            logger.error(f"Eingangsordner nicht gefunden: {IN_FOLDER_XML_INCOMING_API}")
            return 1
        xml_files = sorted(IN_FOLDER_XML_INCOMING_API.glob('*.xml'))

    if not xml_files:
        logger.info("Keine XML-Dateien gefunden.")
        return 0

    total = 0
    for xml_path in xml_files:
        logger.info(f"Verarbeite: {xml_path.name}")
        total += process_xml_file(xml_path, dry_run=args.dry_run)

    mode = "[DRY-RUN] " if args.dry_run else ""
    logger.info(f"Fertig: {mode}{total} neue Snapshot(s) importiert")
    print(f"Fertig, Snapshots importiert: {total}")
    return total


if __name__ == '__main__':
    sys.exit(0 if main() >= 0 else 1)
