import os
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from src.config import get_account_config
from src.db.db_access import DBAccess, TradeRepository
from src.import_activity_statement import import_activity_statement
from src.logger_setup import setup_logging, print_log
from src.parsers.activity_csv_parser import ActivityCsvParser
from src.parsers.flex_parser import process_flex_file
from src.utils.path_utils import get_project_root
from src.utils.progress import ProgressLine

# Eingangsordner — alle eingehenden Dateien landen hier, Routing per accountId
BASE_XML_INCOMING       = r'C:\Trade_XML\incoming'
BASE_CSV_INCOMING       = r'C:\Trade_CSV\incoming'
# Produktions-Basis für processed/ und deleted/ nach dem Import
BASE_XML_FILE_PATH_PROD = r'C:\Trade_XML'

log_file = get_project_root() / "log/app.log"
logger, _ = setup_logging('my_app', level="simple", log_file=log_file)


def import_trades() -> None:
    """
    Importiert alle Trades aus den incoming/-Ordnern.
    Environment und User werden automatisch per accountId-Mapping ermittelt.
    """
    logger.info("=" * 80)
    logger.info(f"Starte Import ({datetime.now().strftime('%Y-%m-%d - %H:%M:%S')})")
    logger.info("=" * 80)

    _import_xml_files()

    cnt_csv = _import_activity_csvs()
    logger.info(f"CSV-Import abgeschlossen: {cnt_csv} Snapshot(s)")


# ---------------------------------------------------------------------------
# XML-Import
# ---------------------------------------------------------------------------

def _read_account_id_from_xml(xml_path: Path) -> str | None:
    """Liest accountId aus dem ersten FlexStatement-Element der XML-Datei."""
    try:
        root = ET.parse(xml_path).getroot()
        stmt = root.find(".//FlexStatement")
        return stmt.get("accountId") if stmt is not None else None
    except Exception as e:
        logger.error(f"Fehler beim Lesen der accountId aus {xml_path.name}: {e}")
        return None


def _ensure_env_dirs(environment: str) -> None:
    """Erstellt processed/ und deleted/ für ein Environment falls nötig."""
    base = Path(BASE_XML_FILE_PATH_PROD) / environment
    for sub in ['processed', 'deleted']:
        (base / sub).mkdir(parents=True, exist_ok=True)


def _import_xml_files() -> None:
    """
    Scannt C:\\Trade_XML\\incoming\\ nach flex.*.xml-Dateien.
    Routing: accountId → ACCOUNT_MAP → environment + table_prefix.
    Verarbeitete Dateien werden nach <env>/processed/ bzw. <env>/deleted/ verschoben.
    """
    incoming = Path(BASE_XML_INCOMING)
    incoming.mkdir(parents=True, exist_ok=True)

    files = [f for f in os.listdir(incoming) if f.lower().startswith("flex.") and f.lower().endswith(".xml")]
    if not files:
        print("Keine XML-Dateien in incoming/ gefunden.")
        return

    progress = ProgressLine(logger)
    total = len(files)
    total_inserted = 0

    for i, xml_file in enumerate(files, start=1):
        xml_path = incoming / xml_file

        raw_id = _read_account_id_from_xml(xml_path)
        if not raw_id:
            logger.warning(f"Keine accountId lesbar: {xml_file} — übersprungen")
            continue

        cfg = get_account_config(raw_id)
        if not cfg:
            logger.warning(f"Unbekannte accountId '{raw_id}' in {xml_file} — übersprungen")
            continue

        environment  = cfg['environment']
        table_prefix = cfg['table_prefix']
        env_up       = environment.upper()

        _ensure_env_dirs(environment)
        db   = DBAccess(logger, environment, table_prefix)
        repo = TradeRepository(db)

        progress.start(f"({i}/{total}): {xml_file} [{env_up} / {table_prefix}]")
        num_inserted, entry_found = process_flex_file(xml_path, db, repo, logger, environment)
        total_inserted += num_inserted
        delete_file = num_inserted == 0 and entry_found == 0
        progress.done(f"({i}/{total}) {xml_file} → {num_inserted} Trades [{env_up}]")

        target_base = Path(BASE_XML_FILE_PATH_PROD) / environment
        move_xml_file(xml_file, incoming, logger, delete_file, target_base)

    logger.info(f"XML-Import abgeschlossen: {total_inserted} Trades aus {total} Datei(en)")


def _import_xml_from_summary(environment: str, table_prefix: str) -> None:
    """
    Legacy-Modus: summary.xml aus <env>/-Verzeichnis importieren.
    Aufruf: python import_ibkr_trades.py from_summary <env> <prefix>
    """
    env_up = environment.upper()
    logger.info("=" * 80)
    logger.info(f"Summary-Import: {env_up} / {table_prefix} ({datetime.now().strftime('%Y-%m-%d - %H:%M:%S')})")
    logger.info("=" * 80)

    summary_path = Path(BASE_XML_FILE_PATH_PROD) / environment / f"summary_{table_prefix}{environment}.xml"
    if not summary_path.exists():
        print(f"summary.xml nicht gefunden: {summary_path}")
        return

    db   = DBAccess(logger, environment, table_prefix)
    repo = TradeRepository(db)

    progress = ProgressLine(logger)
    progress.start(f"Importiere summary.xml [{env_up}]")
    num_inserted, _ = process_flex_file(summary_path, db, repo, logger, environment)
    progress.done(f"summary.xml → {num_inserted} Trades [{env_up}]")
    logger.info(f"Summary-Import abgeschlossen: {num_inserted} Trades [{env_up}]")


# ---------------------------------------------------------------------------
# CSV-Import
# ---------------------------------------------------------------------------

def _import_activity_csvs() -> int:
    """
    Scannt C:\\Trade_CSV\\incoming\\ nach Activity Statement CSVs.
    Routing: accountId aus Dateiinhalt → ACCOUNT_MAP → environment + table_prefix.
    Verarbeitete Dateien werden nach incoming/processed/ verschoben.
    """
    incoming = Path(BASE_CSV_INCOMING)
    incoming.mkdir(parents=True, exist_ok=True)

    csv_files = [f for f in os.listdir(incoming) if f.lower().endswith('.csv')]
    if not csv_files:
        return 0

    processed_dir = incoming / "processed"
    cnt = 0

    for csv_file in csv_files:
        csv_path = incoming / csv_file

        parser = ActivityCsvParser(str(csv_path))
        raw_id = parser.account_id

        if not raw_id:
            logger.warning(f"Keine accountId in {csv_file} — übersprungen")
            continue

        cfg = get_account_config(raw_id)
        if not cfg:
            logger.warning(f"Unbekannte accountId '{raw_id}' in {csv_file} — übersprungen")
            continue

        environment  = cfg['environment']
        table_prefix = cfg['table_prefix']

        imported = import_activity_statement(str(csv_path), environment, table_prefix)
        processed_dir.mkdir(exist_ok=True)
        shutil.move(str(csv_path), str(processed_dir / csv_file))

        if imported:
            cnt += 1

    return cnt


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def move_xml_file(file_name: str, orig_dir: Path, log, delete_files: bool, target_base: Path) -> None:
    """Verschiebt eine XML-Datei von orig_dir nach target_base/processed/ oder target_base/deleted/."""
    orig_path  = orig_dir / file_name
    target_dir = target_base / ("deleted" if delete_files else "processed")
    target_dir.mkdir(parents=True, exist_ok=True)

    if orig_path.exists():
        shutil.move(str(orig_path), str(target_dir / file_name))
        label = "deleted" if delete_files else "processed"
        print_log(log, f"{file_name} → {label}", True)
    else:
        print_log(log, f"Datei nicht gefunden: {orig_path}", True)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args = sys.argv[1:]
    use_summary = "from_summary" in args
    args = [a for a in args if a != "from_summary"]

    if use_summary:
        if len(args) < 2:
            print("from_summary benötigt: <environment> <table_prefix>")
            print("  Beispiel: python import_ibkr_trades.py from_summary money mike_")
            sys.exit(1)
        _import_xml_from_summary(args[0].lower(), args[1])
    else:
        import_trades()
