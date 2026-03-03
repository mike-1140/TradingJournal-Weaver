import os
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime
import sys
import glob

from src.logger_setup import setup_logging
from src.utils.path_utils import get_project_root

# Constants (Make it easier to configure)
BASE_XML_FILE_PATH = r'C:\TradeInfo'
SUMMARY_FILE_NAME = "summary.xml"

# Logging
log_file = get_project_root() / "log/app.log"
logger = setup_logging('my_app', level="simple", log_file=log_file)
logger.info("----  MAKE SUMMARY (" + datetime.now().strftime('%Y-%m-%d - %H:%M:%S') + ")  ----")


def parse_date(date_str: str) -> datetime:
    """Wandelt fromDate (DD/MM/YYYY) in datetime-Objekt um."""
    return datetime.strptime(date_str, "%d/%m/%Y")


def prettify_xml(elem: ET.Element) -> str:
    """Erzeugt formatierten XML-String mit Einrückung."""
    import xml.dom.minidom
    rough_string = ET.tostring(elem, encoding="utf-8")
    reparsed = xml.dom.minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")


def is_statement_empty(statement: ET.Element) -> bool:
    """Prüft, ob FlexStatement keine inhaltlichen Kinder hat."""
    for child in statement:
        if len(child):  # Hat das Kind selbst Inhalt
            return False
    return True


def initialize_summary_file(summary_file: str) -> tuple[ET.Element, ET.Element]:
    """Erstellt ein neues Summary-File mit der richtigen Struktur."""
    summary_root = ET.Element("FlexQueryResponse", {"queryName": "Summary_Report", "type": "AF"})
    summary_statements_elem = ET.SubElement(summary_root, "FlexStatements", {"count": "0"})

    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(prettify_xml(summary_root))

    logger.info(f"Neues Summary-File erstellt: {summary_file}")
    return summary_root, summary_statements_elem


def append_new_days_to_summary(
    input_files: list[str],
    summary_file: str,
    processed_dir: str | None = None,
    delete_dir: str | None = None
) -> bool:
    """
    Hängt alle neuen FlexStatements (fromDate > letztem fromDate im Summary)
    an das Summary-File an. Aktualisiert count, keine Duplikate, keine Merges.
    """
    statements_added = 0
    statements_skipped_empty = 0
    files_moved = 0

    try:
        # Schritt 1: Summary-File laden oder neu erstellen
        if os.path.exists(summary_file):
            try:
                summary_tree = ET.parse(summary_file)
                summary_root = summary_tree.getroot()
                summary_statements_elem = summary_root.find("FlexStatements")

                if summary_statements_elem is None:
                    logger.error(f"Kein <FlexStatements>-Element in {summary_file}")
                    return False

                all_statements = summary_statements_elem.findall("FlexStatement")
                if all_statements:
                    last_from_date = max(parse_date(s.get("fromDate")) for s in all_statements if s.get("fromDate"))
                else:
                    last_from_date = None

                logger.info(f"Letztes fromDate im Summary: {last_from_date or 'none'}")

            except ET.ParseError as e:
                logger.error(f"Fehler beim Parsen von {summary_file}: {e}")
                return False
        else:
            summary_root, summary_statements_elem = initialize_summary_file(summary_file)
            last_from_date = None

        # Schritt 2: Alle Input-Files verarbeiten
        for input_file in input_files:
            logger.info(f"Verarbeite Datei: {input_file}")

            try:
                input_tree = ET.parse(input_file)
                input_root = input_tree.getroot()
                input_statements_elem = input_root.find("FlexStatements")

                if input_statements_elem is None:
                    logger.warning(f"Keine <FlexStatements> in {input_file}")
                    continue

                file_added = 0
                file_skipped = 0

                for statement in input_statements_elem.findall("FlexStatement"):
                    from_date_str = statement.get("fromDate")
                    if not from_date_str:
                        continue

                    if is_statement_empty(statement):
                        file_skipped += 1
                        statements_skipped_empty += 1
                        continue

                    from_date = parse_date(from_date_str)

                    # Nur hinzufügen, wenn neuer Tag
                    if last_from_date is None or from_date > last_from_date:
                        # Tiefe Kopie, um Referenzprobleme zu vermeiden
                        new_stmt = ET.fromstring(ET.tostring(statement))
                        summary_statements_elem.append(new_stmt)
                        statements_added += 1
                        file_added += 1
                        last_from_date = from_date
                        logger.debug(f"Angehängt: {from_date_str}")
                    else:
                        logger.debug(f"Übersprungen (älter/gleich): {from_date_str}")

                logger.info(f"  Neue Statements: {file_added}, Leere übersprungen: {file_skipped}")

                # Datei verschieben
                if processed_dir or delete_dir:
                    dest_dir = processed_dir if file_added > 0 else delete_dir
                    if dest_dir:
                        try:
                            filename = os.path.basename(input_file)
                            dest_path = os.path.join(dest_dir, filename)
                            shutil.move(input_file, dest_path)
                            logger.info(f"Datei verschoben nach {dest_path}")
                            files_moved += 1
                        except Exception as move_err:
                            logger.error(f"Fehler beim Verschieben von {input_file}: {move_err}")

            except ET.ParseError as e:
                logger.error(f"Fehler beim Parsen von {input_file}: {e}")
            except Exception as e:
                logger.error(f"Fehler beim Verarbeiten von {input_file}: {e}")

        # Schritt 3: count aktualisieren
        summary_statements_elem.set("count", str(len(summary_statements_elem.findall("FlexStatement"))))

        # Schritt 4: Summary speichern
        try:
            with open(summary_file, "w", encoding="utf-8") as f:
                f.write(prettify_xml(summary_root))
            logger.info(f"Summary aktualisiert ({summary_statements_elem.get('count')} Statements).")
        except Exception as e:
            logger.error(f"Fehler beim Speichern von {summary_file}: {e}")
            return False

        logger.info(f"Total hinzugefügt: {statements_added}")
        logger.info(f"Leere übersprungen: {statements_skipped_empty}")
        logger.info(f"Dateien verschoben: {files_moved}")

        return True

    except Exception as e:
        logger.critical(f"Kritischer Fehler beim Append-Vorgang: {e}")
        return False


def find_xml_files(directory: str, exclude_file: str | None = None) -> list[str]:
    """
    Find all XML files in a directory, excluding a specific file.
    """
    xml_pattern = os.path.join(directory, "*.xml")
    xml_files = glob.glob(xml_pattern)

    if exclude_file:
        exclude_abs_path = os.path.abspath(exclude_file)
        xml_files = [f for f in xml_files if os.path.abspath(f) != exclude_abs_path]

    xml_files.sort()
    return xml_files


def main():
    """
    Main function to handle command line arguments.
    """
    if len(sys.argv) > 1:
        data_name = sys.argv[1]
    else:
        data_name = 'paper'

    if data_name in ['paper', 'money']:
        input_dir = os.path.join(BASE_XML_FILE_PATH, data_name)
        dir_processed = os.path.join(BASE_XML_FILE_PATH, f"{data_name}_processed")
        dir_deleted = os.path.join(BASE_XML_FILE_PATH, f"{data_name}_deleted")
        file_summary = os.path.join(input_dir, SUMMARY_FILE_NAME)  # Use input_dir instead of data_name
    else:
        print("Invalid argument. Please provide 'paper' or 'money' as an argument.")
        return

    # Ensure directories exist (safer)
    for dir_path in [input_dir, dir_processed, dir_deleted]:
        if dir_path and not os.path.exists(dir_path):
            try:
                os.makedirs(dir_path, exist_ok=True)  # exist_ok prevents errors if it exists
                logger.info(f"Created directory: {dir_path}")
            except OSError as e:
                logger.error(f"Error creating directory {dir_path}: {e}")
                return

    input_files = find_xml_files(input_dir, file_summary)

    if not input_files:
        logger.info(f"No XML files found in directory '{input_dir}' (excluding summary file)")
        print(f"No XML files found in directory '{input_dir}' (excluding summary file)")
        return

    print(f"Found {len(input_files)} XML files in directory '{input_dir}' (excluding summary file)")

    append_new_days_to_summary(input_files, file_summary, processed_dir=dir_processed, delete_dir=dir_deleted)

if __name__ == "__main__":
    main()
