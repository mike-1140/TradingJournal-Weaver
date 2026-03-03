import xml.etree.ElementTree as ET
import os
import argparse
from xml.dom import minidom

from src.utils.path_utils import get_project_root
from src.utils.div_utils import compute_checksum, parse_date, parse_time

# --- Konfiguration ---
INPUT_DIR = get_project_root() / "input"
PROCESSED_DIR = INPUT_DIR / "processed"


def matches_symbol(elem, search_terms, attributes=("underlyingSymbol", "symbol")):
    """
    Prüft, ob ein XML-Element in einem seiner Attribute einen der gesuchten Symbol-Werte enthält.
    """
    for attr in attributes:
        value = elem.get(attr, "").upper()
        if value in search_terms:
            return True
    return False


def remove_empty_elements(elem):
    for child in list(elem):
        remove_empty_elements(child)
        if (len(child) == 0) and (not child.attrib) and (not (child.text and child.text.strip())):
            elem.remove(child)


def extract_elements_by_term(input_file, output_file, search_terms):
    """
    Extrahiert alle Elemente für mehrere Symbole aus dem IBKR-FlexQuery-XML.
    """
    try:
        search_terms = [s.upper() for s in search_terms]

        # Parse XML
        tree = ET.parse(input_file)
        root = tree.getroot()

        # Neue Root-Struktur anlegen
        new_root = ET.Element(root.tag, root.attrib)

        # queryName = Output-Dateiname ohne .xml
        filename_without_ext = os.path.splitext(os.path.basename(output_file))[0]
        new_root.set("queryName", filename_without_ext)

        statements_added = 0
        trades_added = 0
        ca_added = 0

        flex_statements = root.find("FlexStatements")
        if flex_statements is not None:
            new_flex_statements = ET.SubElement(new_root, "FlexStatements", flex_statements.attrib)

            for statement in flex_statements.findall("FlexStatement"):
                new_statement = None

                # --- Trades ---
                for trades in statement.findall("Trades"):
                    new_trades = None
                    for trade in trades.findall("Trade"):
                        if matches_symbol(trade, search_terms):
                            if new_statement is None:
                                new_statement = ET.SubElement(new_flex_statements, "FlexStatement", statement.attrib)
                            if new_trades is None:
                                new_trades = ET.SubElement(new_statement, "Trades")
                            ET.SubElement(new_trades, "Trade", trade.attrib)
                            trades_added += 1

                # --- OptionEAE ---
                for option in statement.findall("OptionEAE"):
                    new_option = None
                    for child in option:
                        if matches_symbol(child, search_terms):
                            if new_statement is None:
                                new_statement = ET.SubElement(new_flex_statements, "FlexStatement", statement.attrib)
                            if new_option is None:
                                new_option = ET.SubElement(new_statement, "OptionEAE")
                            new_option.append(ET.fromstring(ET.tostring(child)))

                # --- CorporateActions ---
                for ca in statement.findall("CorporateActions"):
                    new_ca = None
                    for action in ca.findall("CorporateAction"):
                        if matches_symbol(action, search_terms):
                            if new_statement is None:
                                new_statement = ET.SubElement(new_flex_statements, "FlexStatement", statement.attrib)
                            if new_ca is None:
                                new_ca = ET.SubElement(new_statement, "CorporateActions")
                            ET.SubElement(new_ca, "CorporateAction", action.attrib)
                            ca_added += 1

                if new_statement is not None:
                    statements_added += 1

            # Count aktualisieren
            new_flex_statements.set("count", str(statements_added))

        # --- Ausgabe formatieren ---
        xml_str = ET.tostring(new_root, encoding="unicode")
        pretty_xml = minidom.parseString(xml_str).toprettyxml(indent="  ")
        pretty_lines = [line for line in pretty_xml.split("\n") if line.strip()]
        pretty_xml = "\n".join(pretty_lines)

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(pretty_xml)

        print(f"Extraktion abgeschlossen → {output_file}")
        print(f"{statements_added} FlexStatements enthalten {search_terms}")
        print(f"{trades_added} Trades extrahiert")
        print(f"{ca_added} CorporateActions extrahiert")

        return True

    except Exception as e:
        print(f"Fehler beim Verarbeiten: {str(e)}")
        return False


def generate_output_filename(search_terms):
    # Alle Symbole verbinden → z. B. KO_PEP_AAPL.xml
    joined = "_".join(s.upper() for s in search_terms)
    return os.path.join(INPUT_DIR, f"{joined}.xml")


def main():
    """
    Main function to handle command line arguments
    """
    default_input = r"summary.xml"

    parser = argparse.ArgumentParser(
        description="Extract elements from XML file based on one or more search terms"
    )
    parser.add_argument(
        "-t", "--term",
        required=True,
        nargs="+",   # mehrere Symbole erlaubt
        help="Search term(s) to extract, only in 'underlyingSymbol' (e.g., KO PEP AAPL)"
    )
    parser.add_argument(
        "-s", "--source",
        required=True,
        help="Search source to extract Symbol"
    )

    args = parser.parse_args()

    if len(args.source) > 1:
        data_name = args.source
    else:
        data_name = "test"

    if data_name in ["test", "paper", "money"]:
        # SUMMARY_FILE = f"C:/TradeInfo/{data_name}/summary.xml"
        SUMMARY_FILE = f"C:/TradeInfo/{data_name}/summary.xml"
        SUMMARY_FILE = f"C:/Users/Mike/PycharmProjects/pythonProject/xml_proj/input/flex/flex.1138728.money_30_report.20250818.20250916.xml"
        print(f"Extraktion gestartet → {SUMMARY_FILE}")
        output_filename = generate_output_filename(args.term)
        extract_elements_by_term(SUMMARY_FILE, output_filename, args.term)
    else:
        print(f"No SUMMARY-File found in directory '{data_name}'")
        return



if __name__ == "__main__":
    main()
