import xml.etree.ElementTree as ET
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))  # xml_proj/ in sys.path

import glob
import shutil
from xml.dom import minidom
import hashlib  # Für Hash-Berechnung
from datetime import datetime
import re

from src.logger_setup import setup_logging
from src.utils.path_utils import get_project_root
from src.utils.div_utils import compute_checksum, parse_datetime_flex

# Constants (Make it easier to configure)
BASE_XML_FILE_PATH = r'C:\TradeInfo'
SUMMARY_FILE_NAME = "summary.xml"

# Logging
log_file = get_project_root() / "log/app.log"
logger, _ = setup_logging('my_app', level="simple", log_file=log_file)
logger.info("----  MAKE SUMMARY (" + datetime.now().strftime('%Y-%m-%d - %H:%M:%S') + ")  ----")

# Einheitliche Zahlenerkennung (mit Tausendertrennzeichen)
NUMBER_PATTERN = re.compile(r'^-?[\d,]+(?:\.\d+)?$')

# Felder, die beim Hash ignoriert werden sollen
IGNORED_FIELDS = {"accountId", "volatilityOrderLink", "orderReference", "exchOrderId", "extExecID",
                  "holdingPeriodDateTime", "whenRealized", "whenReopened"}


def normalize_number_string(value: str, decimal_places=2) -> str:
    """
    Normalisiert einen numerischen String:
    - Entfernt Tausendertrennzeichen
    - Formatiert Ganzzahlen ohne Nachkommastellen
    - Formatiert Floats mit fixer Anzahl Dezimalstellen
    """
    val = value.strip()
    if NUMBER_PATTERN.match(val):
        clean_val = val.replace(",", "")
        try:
            num = float(clean_val)
            if num.is_integer():
                return str(int(num))
            else:
                return f"{num:.{decimal_places}f}"
        except ValueError:
            return value
    return value


def is_statement_empty(statement: ET.Element) -> bool:
    """
    Check if a FlexStatement is empty (has no meaningful content).
    """
    if any(trades.findall('Trade') for trades in statement.findall('Trades')):
        return False
    if any(ca.findall('CorporateAction') for ca in statement.findall('CorporateActions')):
        return False
    if any(statement.findall('OptionEAE/*')):  # Checks for ANY child of OptionEAE
        return False

    return True  # Statement is empty if none of the above conditions are met


def initialize_summary_file(template_file: str, summary_file: str) -> tuple[ET.Element, ET.Element, dict]:
    """
    Initialize a new summary file using the structure from a template file.
    """
    try:
        template_tree = ET.parse(template_file)
        template_root = template_tree.getroot()
    except ET.ParseError as e:
        logger.error(f"Error parsing template file {template_file}: {e}")
        raise  # Re-raise the exception to stop processing

    # Create a new document with the same root tag and attributes
    summary_root = ET.Element(template_root.tag, template_root.attrib)

    # Find or create the FlexStatements element
    template_statements = template_root.find('FlexStatements')
    if template_statements is not None:
        summary_statements_elem = ET.SubElement(summary_root, 'FlexStatements', template_statements.attrib)
    else:
        summary_statements_elem = ET.SubElement(summary_root, 'FlexStatements')

    existing_statements_dict = {}  # Dictionary to store statements by date

    return summary_root, summary_statements_elem, existing_statements_dict


def prettify_xml(element: ET.Element) -> str:
    """
    Return a pretty-printed XML string for the Element.
    """
    try:
        xml_str = ET.tostring(element, encoding='utf-8').decode('utf-8')
        dom = minidom.parseString(xml_str)
        pretty_xml = dom.toprettyxml(indent="  ")

        # Remove extra blank lines
        pretty_lines = [line for line in pretty_xml.split('\n') if line.strip()]
        return '\n'.join(pretty_lines)
    except Exception as e:
        logger.error(f"Error prettifying XML: {e}")
        return ET.tostring(element, encoding='unicode')  # Return unformatted XML as a fallback


def normalize_element_numbers(elem, decimal_places=2):
    """
    Normalisiert alle numerischen Attribute eines Elements.
    """
    for attr, value in elem.attrib.items():
        elem.attrib[attr] = normalize_number_string(value, decimal_places)
    return elem


def calculate_element_hash(element, decimal_places=2):
    """
    Erzeugt einen Hash eines Elements basierend auf normalisierten Attributen.
    """
    attrib_items = sorted(
        (k, normalize_number_string(v, decimal_places))
        for k, v in element.attrib.items()
        if k not in IGNORED_FIELDS
    )
    attrib_string = "".join(f"{k}={v}" for k, v in attrib_items)
    return hashlib.md5(attrib_string.encode("utf-8")).hexdigest()


def merge_statement_elements(source_statement, target_statement, decimal_places=2):
    """
    Merged Elemente zwischen zwei Statements:
    - Normalisiert Zahlen
    - Vermeidet Duplikate
    - Normalisiert am Ende nochmal den gesamten Zielbaum
    """
    elements_added = 0

    def process_elements(tag_name):
        nonlocal elements_added
        source_parent = source_statement.find(tag_name)
        if source_parent is not None and len(source_parent) > 0:
            target_parent = target_statement.find(tag_name)
            if target_parent is None:
                target_parent = ET.SubElement(target_statement, tag_name)

            existing_hashes = {calculate_element_hash(el, decimal_places) for el in target_parent}

            for elem in source_parent:
                normalize_element_numbers(elem, decimal_places)  # immer normalisieren
                elem_hash = calculate_element_hash(elem, decimal_places)
                if elem_hash not in existing_hashes:
                    target_parent.append(elem)
                    existing_hashes.add(elem_hash)
                    elements_added += 1

    # Bearbeite die relevanten Sektionen
    process_elements("Trade")
    process_elements("CorporateAction")
    process_elements("OptionEAE")

    # Final: den ganzen Zielbaum normalisieren (sicherstellen, dass alles sauber ist)
    for parent_tag in ["Trade", "CorporateAction", "OptionEAE"]:
        parent_elem = target_statement.find(parent_tag)
        if parent_elem is not None:
            for child in parent_elem:
                normalize_element_numbers(child, decimal_places)

    return elements_added


def merge_xml_files(input_files: list[str], summary_file: str, processed_dir: str | None = None,
                    delete_dir: str | None = None) -> bool:
    """
    Merge non-empty FlexStatements from input_files into summary_file.
    For statements with same fromDate, merge their contents without duplicates.
    Sort statements chronologically based on fromDate.
    Optionally move processed files.
    """
    statements_added = 0
    elements_merged = 0
    statements_skipped_empty = 0
    files_moved = 0
    statement_dict = {}  # Use a dictionary to store statements by date

    try:
        # Load existing summary or initialize a new one
        if os.path.exists(summary_file):
            try:
                summary_tree = ET.parse(summary_file)
                summary_root = summary_tree.getroot()
                summary_statements_elem = summary_root.find('FlexStatements')
                if summary_statements_elem is None:
                    logger.error(f"No FlexStatements element found in existing summary file {summary_file}")
                    return False

                # Store existing statements in dictionary by fromDate
                for stmt in summary_statements_elem.findall('FlexStatement'):
                    from_date = stmt.get('fromDate')
                    if from_date:
                        statement_dict[from_date] = stmt

                # Remove all existing statements - we'll re-add them in sorted order
                for stmt in list(summary_statements_elem):  # Create a list to avoid modification issues
                    if stmt.tag == 'FlexStatement':
                        summary_statements_elem.remove(stmt)

                logger.info(f"Summary file contains {len(statement_dict)} unique dates")

            except ET.ParseError as e:
                logger.error(f"Error parsing existing summary file {summary_file}: {e}")
                return False

        else:
            if not input_files:
                logger.error("No input files provided and summary file doesn't exist.")
                return False
            try:
                summary_root, summary_statements_elem, statement_dict = initialize_summary_file(input_files[0],
                                                                                                summary_file)
                logger.info("Created new summary file structure")
            except Exception:
                # initialize_summary_file logs the error; we just need to stop here
                return False

        # Process each input file
        for input_file in input_files:
            logger.info(f"Processing file: {input_file}")
            try:
                input_tree = ET.parse(input_file)
                input_root = input_tree.getroot()
                input_statements = input_root.find('FlexStatements')

                if input_statements is None:
                    logger.warning(f"No FlexStatements element found in {input_file}")
                    continue

                file_added = 0
                file_merged = 0
                file_skipped_empty = 0

                for statement in input_statements.findall('FlexStatement'):
                    from_date = statement.get('fromDate')

                    if is_statement_empty(statement):
                        file_skipped_empty += 1
                        statements_skipped_empty += 1
                        logger.debug(f"Skipped empty statement with fromDate: {from_date}")
                        continue

                    if from_date in statement_dict:
                        # We already have a statement for this date - merge the content
                        elements_added = merge_statement_elements(statement_dict[from_date], statement)
                        if elements_added > 0:
                            file_merged += elements_added
                            elements_merged += elements_added
                            logger.debug(
                                f"Merged {elements_added} elements with fromDate: {from_date}")
                    else:
                        # This is a new date - add it to our dictionary
                        statement_dict[from_date] = statement
                        file_added += 1
                        statements_added += 1
                        logger.debug(f"Added statement with fromDate: {from_date}")

                logger.info(
                    f"  Added: {file_added} statements, Merged: {file_merged} elements, Skipped empty: {file_skipped_empty}")

                # Move files after processing
                if processed_dir or delete_dir:
                    dest_dir = processed_dir if (file_added > 0 or file_merged > 0) else delete_dir
                    if dest_dir:
                        try:
                            filename = os.path.basename(input_file)
                            dest_path = os.path.join(dest_dir, filename)
                            shutil.move(input_file, dest_path)
                            logger.info(f"Moved to {dest_path}")
                            files_moved += 1
                        except Exception as move_err:
                            logger.error(f"Error moving {input_file}: {move_err}")

            except ET.ParseError as parse_err:
                logger.error(f"Error parsing {input_file}: {parse_err}")
            except Exception as file_err:
                logger.error(f"Error processing {input_file}: {file_err}")

        # Sort all statements by date and add them back to the summary
        sorted_dates = sorted(statement_dict.keys(), key=lambda date_str: parse_datetime_flex(date_str, logger))

        for date in sorted_dates:
            summary_statements_elem.append(statement_dict[date])

        # Save the updated summary file
        try:
            pretty_xml = prettify_xml(summary_root)
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(pretty_xml)
            logger.info(f"Summary complete. Results saved to {summary_file}")
        except Exception as save_err:
            logger.error(f"Error saving summary file: {save_err}")
            return False

        logger.info(f"Total added: {statements_added}")
        logger.info(f"Total elements merged: {elements_merged}")
        logger.info(f"Total skipped empty: {statements_skipped_empty}")
        logger.info(f"Total files moved: {files_moved}")

        return True

    except Exception as overall_err:
        logger.critical(f"Critical error during XML processing: {overall_err}")  # Use critical for unrecoverable errors
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

    if data_name in ['test', 'paper', 'money', 'autom_money', 'autom_paper']:
        input_dir = os.path.join(BASE_XML_FILE_PATH, data_name)
        dir_processed = os.path.join(BASE_XML_FILE_PATH, f"{data_name}_processed")
        dir_deleted = os.path.join(BASE_XML_FILE_PATH, f"{data_name}_deleted")
        file_summary = os.path.join(input_dir, SUMMARY_FILE_NAME)  # Use input_dir instead of data_name
    else:
        print("Invalid argument. Please provide 'test', 'paper', 'money', 'autom_money' or 'autom_paper' as an argument.")
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

    merge_xml_files(input_files, file_summary, processed_dir=dir_processed, delete_dir=dir_deleted)


if __name__ == "__main__":
    main()
