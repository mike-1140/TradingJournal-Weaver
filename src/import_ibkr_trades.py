from pathlib import Path

import pandas as pd
import sys
import xml.etree.ElementTree as ET
import os
from datetime import datetime
import uuid
import os
import shutil

from src.logger_setup import setup_logging, print_log
from src.utils.path_utils import get_project_root
from src.utils.progress import ProgressLine
from src.utils.div_utils import compute_checksum, \
    parse_datetime_flex  # parse_date, parse_time,watch_fields, smart_print
from src.parsers.flex_parser import process_flex_file
from src.db.db_access import DBAccess, TradeRepository
from src.config import TABLE_PREFIX

# Constants (Make it easier to configure)
BASE_XML_FILE_PATH_PROD = r'C:\Trade_XML'
BASE_XML_FILE_PATH_TEST = get_project_root() / "input"
# Logging
log_file = get_project_root() / "log/app.log"
logger, _ = setup_logging('my_app', level="simple", log_file=log_file)


def import_trades(environment: str, table_pref: str, use_summary: bool = False) -> None:
    """
    Importiert Trades, OptionEAE, CorporateActions und FX aus XML-Dateien.
    environment: 'test' oder 'prod' (case-insensitive)
    use_summary: True → summary.xml importieren statt flex.*.xml (kein Verschieben)
    """
    environment = environment.lower()
    env_up = environment.upper()

    logger.info("=" * 80)
    logger.info(f"Starte Import für Environment: {env_up} mit Präfix: '{table_pref}' (" + datetime.now().strftime('%Y-%m-%d - %H:%M:%S') + ")")
    logger.info("=" * 80)

    db = DBAccess(logger, environment, table_pref)
    repo = TradeRepository(db)

    base_xml_path = BASE_XML_FILE_PATH_TEST if environment == "test" else BASE_XML_FILE_PATH_PROD
    input_dir = Path(base_xml_path) / environment

    if environment in ['paper', 'money', 'autom_money', 'autom_paper']:
        dir_processed = input_dir / "processed"
        dir_deleted   = input_dir / "deleted"

        # Ensure directories exist (safer)
        for dir_path in [input_dir, dir_processed, dir_deleted]:
            if dir_path and not os.path.exists(dir_path):
                try:
                    os.makedirs(dir_path, exist_ok=True)  # exist_ok prevents errors if it exists
                    logger.info(f"Created directory: {dir_path}")
                except OSError as e:
                    logger.error(f"Error creating directory {dir_path}: {e}")
                    return

    elif environment in ['test']:
        pass
    else:
        print("Invalid argument. Please provide 'test', 'paper' or 'money' as an argument.")
        return

    if use_summary:
        summary_path = input_dir / "summary.xml"
        if not summary_path.exists():
            print(f"summary.xml nicht gefunden: {summary_path}")
            return
        files = ["summary.xml"]
    else:
        files = [f for f in os.listdir(input_dir) if f.lower().startswith("flex.") and f.lower().endswith(".xml")]

    if not files:
        print("Keine XML-Dateien gefunden.")
        return

    progress = ProgressLine(logger)
    total_files = len(files)
    total_inserted = 0

    for i, xml_file in enumerate(files, start=1):
        xml_path_file = Path(input_dir) / xml_file
        progress.start(f"Importiere ({i}/{total_files}): {xml_file}")
        num_inserted, entry_found = process_flex_file(xml_path_file, db, repo, logger, environment)
        total_inserted += num_inserted
        delete_files = num_inserted == 0 and entry_found == 0
        progress.done(f"({i}/{total_files}) {xml_file}  →  {num_inserted} Trades importiert")
        if not use_summary:
            move_xml_file(environment, xml_file, Path(input_dir), logger, delete_files)

    # Logging am Ende
    logger.info(f"Import abgeschlossen: {total_inserted} Trades aus {total_files} Datei(en) [{env_up}]")


def move_xml_file(environment: str, file_name, orig_dir, log, delete_files=False):
    """
    Verschiebt eine XML-Datei aus orig_dir entweder nach 'processed'
    oder 'deleted', abhängig von delete_files.
    """

    # Pfade aufbauen
    orig_path = os.path.join(str(orig_dir), str(file_name))

    processed_dir = os.path.join(orig_dir, "processed")
    deleted_dir = os.path.join(orig_dir, "deleted")

    # Zielverzeichnis abhängig vom Parameter
    target_dir = deleted_dir if delete_files else processed_dir
    target_txt = "deleted" if delete_files else "processed"

    # Zielpfad
    target_path = os.path.join(target_dir, file_name)

    # Sicherstellen, dass die Zielordner existieren
    # sollte schon alles da sein
    os.makedirs(target_dir, exist_ok=True)

    # Datei verschieben
    if os.path.exists(orig_path):
        if environment in ['test']:
            pass
        else:
            shutil.move(orig_path, target_path)
        print_log(log, f"{file_name} verschoben nach: {target_txt}", True)
    else:
        print_log(log, f"Datei existiert nicht: {orig_path}", True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Bitte Environment angeben: money | paper | test | autom_money | autom_paper")
        print("Optional: Table-Prefix,   z.B.: python import_ibkr_trades.py money mike_")
        print("Optional: from_summary    → summary.xml importieren statt flex.*.xml")
        table_prefix = "mike_"
        env = "test"
        use_summary = False
        # sys.exit(1)
    else:
        # from_summary kann als letztes Argument stehen
        args = sys.argv[1:]
        use_summary = "from_summary" in args
        args = [a for a in args if a != "from_summary"]

        if len(args) >= 2:
            # --- OPTIONALER TABLE PREFIX ÜBER COMMANDLINE ---
            table_prefix = args[1]
            print(f"*** TABLE PREFIX via Commandline aktiv: '{table_prefix}' ***")
            env = args[0].lower()
        else:
            table_prefix = TABLE_PREFIX
            env = args[0].lower()

    import_trades(env, table_prefix, use_summary=use_summary)
