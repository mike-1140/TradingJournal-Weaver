import os
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from src.config import TABLE_PREFIX, get_account_config, is_environment_active, load_active_targets
from src.db.db_access import DBAccess, TradeRepository
from src.import_activity_statement import import_activity_statement
from src.logger_setup import setup_logging, print_log
from src.parsers.activity_csv_parser import ActivityCsvParser
from src.parsers.flex_parser import process_flex_file
from src.utils.path_utils import get_project_root
from src.utils.progress import ProgressLine

# Eingangsordner — alle eingehenden Dateien landen hier, Routing per accountId.
# Zwei Quellen (Mail + API), fuer den Import gleichwertig behandelt (siehe _import_xml_files):
# gleiches Routing, gleiche processed/deleted-Ablage, kein Filename-Unterschied noetig.
BASE_XML_INCOMING_MAIL   = r'C:\Trade_XML\incoming_mail'
BASE_XML_INCOMING_API    = r'C:\Trade_XML\incoming_api'
BASE_CSV_INCOMING        = r'C:\Trade_CSV\incoming'
# Produktions-Basis für processed/ und deleted/ nach dem Import
BASE_XML_FILE_PATH_PROD = r'C:\Trade_XML'

log_file = get_project_root() / "log/app.log"
logger, _ = setup_logging('my_app', level="simple", log_file=log_file)


def import_trades(target_environment: str | None = None, target_table_prefix: str | None = None) -> None:
    """
    Importiert alle Trades aus den incoming/-Ordnern.
    Environment und User werden automatisch per accountId-Mapping ermittelt.

    Mit target_environment/target_table_prefix (CLI-Override, analog process_ibkr_trades.py):
    nur Dateien fuer genau dieses Environment/Prefix werden importiert+verschoben, alle
    anderen bleiben unangetastet in incoming_mail/incoming_api liegen (fuer den naechsten
    Lauf ohne Filter oder mit anderem Ziel).
    """
    logger.info("=" * 80)
    logger.info(f"Starte Import ({datetime.now().strftime('%Y-%m-%d - %H:%M:%S')})")
    logger.info("=" * 80)

    _import_xml_files(target_environment, target_table_prefix)

    # TEST-Import: eigene Verzeichnisse pro User, kein accountId-Routing
    for t in load_active_targets():
        if t["environment"] != "test":
            continue
        if target_environment and (target_environment != "test" or target_table_prefix != t["prefix"]):
            continue
        cnt_test = _import_test_files(t["prefix"], t["user"])
        logger.info(f"TEST-Import [{t['user']}] abgeschlossen: {cnt_test} Trade(s)")

    cnt_csv = _import_activity_csvs(target_environment, target_table_prefix)
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


def _ensure_env_dirs(environment: str, user: str = "") -> None:
    """Erstellt processed/ und deleted/ für ein Environment (optional mit User-Unterordner)."""
    base = Path(BASE_XML_FILE_PATH_PROD) / environment
    if user:
        base = base / user
    for sub in ['processed', 'deleted']:
        (base / sub).mkdir(parents=True, exist_ok=True)


def _import_xml_files(target_environment: str | None = None, target_table_prefix: str | None = None) -> None:
    """
    Scannt incoming_mail/ und incoming_api/ nach *.xml-Dateien — die Quelle ist fuer
    den Import irrelevant, beide werden identisch behandelt (gleiches Routing, gleiche
    processed/deleted-Ablage). incoming_mail zuerst (vollstaendigere Reports mit
    OptionEAE/BookTrades/CorporateActions), incoming_api danach — Trades sind dank
    Checksum-Dedup (tradeID+dateTime+symbol+quantity+tradePrice) in flex_parser.py
    unabhaengig von der Reihenfolge sicher gegen doppeltes Einfuegen.
    Routing: accountId -> accounts.toml (get_account_config()) -> environment + user + table_prefix.
    Verarbeitete Dateien werden nach <env>/<user>/processed/ bzw. <env>/<user>/deleted/ verschoben.

    Mit target_environment/target_table_prefix: Dateien anderer Environments/Prefixe werden
    uebersprungen und bleiben unverschoben liegen (kein processed/deleted fuer sie).
    """
    total_inserted = 0
    total_files = 0

    for source in (BASE_XML_INCOMING_MAIL, BASE_XML_INCOMING_API):
        incoming = Path(source)
        incoming.mkdir(parents=True, exist_ok=True)

        files = [f for f in os.listdir(incoming) if f.lower().endswith(".xml")]
        if not files:
            print(f"Keine XML-Dateien in {incoming}\\ gefunden.")
            continue

        progress = ProgressLine(logger)
        total = len(files)
        total_files += total

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
            user         = cfg['user']

            if target_environment and (environment != target_environment or table_prefix != target_table_prefix):
                logger.info(
                    f"{xml_file}: gehört zu [{environment.upper()} / {user}], "
                    f"nicht Ziel [{target_environment.upper()} / {target_table_prefix}] — übersprungen (bleibt liegen)"
                )
                continue

            if not is_environment_active(environment, table_prefix):
                logger.info(f"Environment '{environment}' inaktiv (pipeline.toml) — {xml_file} übersprungen")
                continue
            env_up       = environment.upper()

            _ensure_env_dirs(environment, user)
            db   = DBAccess(logger, environment, table_prefix)
            repo = TradeRepository(db)

            progress.start(f"({i}/{total}): {xml_file} [{env_up} / {user}]")
            num_inserted, entry_found = process_flex_file(xml_path, db, repo, logger, environment)
            total_inserted += num_inserted
            delete_file = num_inserted == 0 and entry_found == 0
            progress.done(f"({i}/{total}) {xml_file} -> {num_inserted} Trades [{env_up} / {user}]")

            target_base = Path(BASE_XML_FILE_PATH_PROD) / environment / user
            move_xml_file(xml_file, incoming, logger, delete_file, target_base)

    logger.info(f"XML-Import abgeschlossen: {total_inserted} Trades aus {total_files} Datei(en)")


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
    progress.done(f"summary.xml -> {num_inserted} Trades [{env_up}]")
    logger.info(f"Summary-Import abgeschlossen: {num_inserted} Trades [{env_up}]")


# ---------------------------------------------------------------------------
# TEST-Import (manuelles Environment, kein accountId-Routing)
# ---------------------------------------------------------------------------

def _get_test_prefix() -> str:
    """Liest den Test-Prefix aus pipeline.toml, Fallback auf TABLE_PREFIX."""
    for t in load_active_targets():
        if t["environment"] == "test":
            return t["prefix"]
    return TABLE_PREFIX


def _import_xml_to_test(prefix: str, incoming: Path, target_base: Path) -> int:
    """
    Importiert alle flex.*.xml-Dateien aus 'incoming' in die test-DB.
    Kein accountId-Routing — alles landet in test/{prefix}.
    Verarbeitete Dateien wandern nach target_base/processed/ bzw. deleted/.
    """
    files = [f for f in os.listdir(incoming) if f.lower().startswith("flex.") and f.lower().endswith(".xml")]
    if not files:
        print(f"Keine XML-Dateien gefunden in: {incoming}")
        return 0

    db   = DBAccess(logger, "test", prefix)
    repo = TradeRepository(db)

    progress       = ProgressLine(logger)
    total          = len(files)
    total_inserted = 0

    for i, xml_file in enumerate(files, start=1):
        xml_path = incoming / xml_file
        progress.start(f"TEST ({i}/{total}): {xml_file} [{prefix}]")
        num_inserted, entry_found = process_flex_file(xml_path, db, repo, logger, "test")
        total_inserted += num_inserted
        delete_file = num_inserted == 0 and entry_found == 0
        progress.done(f"TEST ({i}/{total}) {xml_file} -> {num_inserted} Trades")
        move_xml_file(xml_file, incoming, logger, delete_file, target_base)

    return total_inserted


def _import_test_files(prefix: str, user: str) -> int:
    """
    Scannt C:\\Trade_XML\\test\\<user>\\incoming\\ nach flex.*.xml-Dateien.
    Kein accountId-Routing — Environment und User sind durch das Verzeichnis fixiert
    (eigener Ordner je [[test]]-Eintrag aus pipeline.toml, damit mehrere User nicht
    dieselben Dateien wegschnappen).
    """
    target_base = Path(BASE_XML_FILE_PATH_PROD) / "test" / user
    incoming = target_base / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    return _import_xml_to_test(prefix, incoming, target_base)


# ---------------------------------------------------------------------------
# CSV-Import
# ---------------------------------------------------------------------------

def _import_activity_csvs(target_environment: str | None = None, target_table_prefix: str | None = None) -> int:
    """
    Scannt C:\\Trade_CSV\\incoming\\ nach Activity Statement CSVs.
    Routing: accountId aus Dateiinhalt -> accounts.toml (get_account_config()) -> environment + user + table_prefix.
    Verarbeitete Dateien werden nach incoming/<user>/processed/ verschoben.

    Mit target_environment/target_table_prefix: CSVs anderer Environments/Prefixe werden
    uebersprungen und bleiben liegen.
    """
    incoming = Path(BASE_CSV_INCOMING)
    incoming.mkdir(parents=True, exist_ok=True)

    csv_files = [f for f in os.listdir(incoming) if f.lower().endswith('.csv')]
    if not csv_files:
        return 0

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
        user         = cfg['user']

        if target_environment and (environment != target_environment or table_prefix != target_table_prefix):
            logger.info(
                f"{csv_file}: gehört zu [{environment.upper()} / {user}], "
                f"nicht Ziel [{target_environment.upper()} / {target_table_prefix}] — übersprungen (bleibt liegen)"
            )
            continue

        imported = import_activity_statement(str(csv_path), environment, table_prefix)
        processed_dir = incoming / user / "processed"
        processed_dir.mkdir(parents=True, exist_ok=True)
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
        print_log(log, f"{file_name} -> {label}", True)
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

    elif args and args[0].lower() == "test":
        # Test-Modus: alle XMLs aus incoming_mail/ -> test-DB, ohne accountId-Routing
        # Aufruf: python import_ibkr_trades.py test [prefix]
        # Ohne prefix: Wert aus pipeline.toml oder TABLE_PREFIX aus .env
        prefix = args[1] if len(args) > 1 else _get_test_prefix()
        logger.info(f"TEST-Modus: importiere aus incoming_mail/ -> test / {prefix}")
        cnt = _import_xml_to_test(prefix, Path(BASE_XML_INCOMING_MAIL), Path(BASE_XML_FILE_PATH_PROD) / "test")
        logger.info(f"TEST-Import abgeschlossen: {cnt} Trade(s)")

    elif args:
        # CLI-Override: gezielt ein Environment/Prefix importieren (analog process_ibkr_trades.py).
        # Dateien anderer Environments/Prefixe bleiben unangetastet in incoming_mail/incoming_api liegen.
        env          = args[0].lower()
        table_prefix = args[1] if len(args) > 1 else TABLE_PREFIX
        logger.info(f"CLI-Modus: {env} / {table_prefix}")
        import_trades(target_environment=env, target_table_prefix=table_prefix)

    else:
        # Auto-Modus: alle Environments/Prefixe (accountId-Routing entscheidet)
        import_trades()
