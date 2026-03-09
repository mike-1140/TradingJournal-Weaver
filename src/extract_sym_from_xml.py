import xml.etree.ElementTree as ET
import os
import argparse
from xml.dom import minidom
from pathlib import Path

import hashlib

from src.utils.path_utils import get_project_root

# Verzeichnisstruktur analog zu import_ibkr_trades.py
BASE_XML_FILE_PATH_PROD = r'C:\Trade_XML'
BASE_XML_FILE_PATH_TEST = get_project_root() / "input"
OUTPUT_DIR = get_project_root() / "input"


def matches_symbol(elem, search_terms):
    """Prüft ob ein XML-Element das gesuchte underlyingSymbol (oder symbol) enthält."""
    value = elem.get("underlyingSymbol", elem.get("symbol", "")).upper()
    return value in search_terms


def dedup_key(elem, elem_type):
    """
    Berechnet einen stabilen Deduplizierungsschlüssel für ein XML-Element.
    Kontonummer und andere volatile Felder werden bewusst ausgeschlossen.

    Trade:          tradeID (eindeutig bei IBKR) → Fallback: dateTime|symbol|qty|price
    OptionEAE:      transactionID → Fallback: date|symbol|quantity|tradePrice
    CorporateAction: transactionID → Fallback: reportDate|symbol|type|quantity
    """
    if elem_type == "trade":
        trade_id = elem.get("tradeID", "")
        if trade_id:
            return f"T|{trade_id}"
        fields = ["dateTime", "symbol", "quantity", "tradePrice"]

    elif elem_type == "option":
        txn_id = elem.get("transactionID", "")
        if txn_id:
            return f"O|{txn_id}"
        fields = ["date", "symbol", "quantity", "tradePrice"]

    else:  # CorporateAction
        txn_id = elem.get("transactionID", "")
        if txn_id:
            return f"C|{txn_id}"
        fields = ["reportDate", "symbol", "type", "quantity"]

    raw = "|".join(elem.get(f, "") for f in fields)
    return hashlib.md5(raw.encode()).hexdigest()


def get_input_files(environment):
    """
    Gibt alle flex.*.xml Dateien aus dem Environment-Verzeichnis zurück.
    Liest sowohl aktive Dateien als auch bereits verarbeitete (processed/).
    """
    if environment == "test":
        base = Path(BASE_XML_FILE_PATH_TEST)
    else:
        base = Path(BASE_XML_FILE_PATH_PROD)

    input_dir = base / environment
    processed_dir = input_dir / "processed"

    files = []
    for directory in [input_dir, processed_dir]:
        if directory.exists():
            files += [
                directory / f
                for f in os.listdir(directory)
                if f.lower().startswith("flex.") and f.lower().endswith(".xml")
            ]

    return sorted(files)


def collect_by_statement(input_files, search_terms):
    """
    Sammelt passende Elemente gruppiert nach FlexStatement (Periode).
    Gleiche Perioden aus verschiedenen Dateien werden zusammengeführt.
    Duplikate (tradeID / transactionID) werden global übersprungen.
    Gibt eine nach fromDate sortierte Liste von Statement-Dicts zurück:
      [{"attrib": {...}, "trades": [...], "options": [...], "cas": [...]}, ...]
    """
    # Schlüssel: fromDate|toDate — fasst gleiche Perioden aus verschiedenen Dateien zusammen
    stmt_map = {}
    seen_trades, seen_options, seen_cas = set(), set(), set()
    skipped = 0

    for path in input_files:
        try:
            tree = ET.parse(path)
            root = tree.getroot()
            flex_statements = root.find("FlexStatements")
            if flex_statements is None:
                continue

            for statement in flex_statements.findall("FlexStatement"):
                stmt_key = statement.get("fromDate", "") + "|" + statement.get("toDate", "")

                stmt_trades, stmt_options, stmt_cas = [], [], []

                for trades_elem in statement.findall("Trades"):
                    for trade in trades_elem.findall("Trade"):
                        if matches_symbol(trade, search_terms):
                            key = dedup_key(trade, "trade")
                            if key in seen_trades:
                                skipped += 1
                                continue
                            seen_trades.add(key)
                            stmt_trades.append(trade)

                for opt_elem in statement.findall("OptionEAE"):
                    for child in opt_elem:
                        if matches_symbol(child, search_terms):
                            key = dedup_key(child, "option")
                            if key in seen_options:
                                skipped += 1
                                continue
                            seen_options.add(key)
                            stmt_options.append(child)

                for ca_elem in statement.findall("CorporateActions"):
                    for action in ca_elem.findall("CorporateAction"):
                        if matches_symbol(action, search_terms):
                            key = dedup_key(action, "ca")
                            if key in seen_cas:
                                skipped += 1
                                continue
                            seen_cas.add(key)
                            stmt_cas.append(action)

                if stmt_trades or stmt_options or stmt_cas:
                    if stmt_key not in stmt_map:
                        stmt_map[stmt_key] = {
                            "attrib": dict(statement.attrib),
                            "trades": [],
                            "options": [],
                            "cas": [],
                        }
                    stmt_map[stmt_key]["trades"].extend(stmt_trades)
                    stmt_map[stmt_key]["options"].extend(stmt_options)
                    stmt_map[stmt_key]["cas"].extend(stmt_cas)

        except Exception as ex:
            print(f"Fehler beim Lesen von {path}: {ex}")

    if skipped:
        print(f"  {skipped} Duplikat(e) übersprungen")

    # FlexStatements chronologisch sortieren
    sorted_stmts = sorted(stmt_map.values(), key=lambda s: s["attrib"].get("fromDate", ""))

    # Innerhalb jedes Statements ebenfalls chronologisch sortieren
    for stmt in sorted_stmts:
        stmt["trades"].sort(key=lambda x: x.get("dateTime", x.get("tradeDate", "")))
        stmt["options"].sort(key=lambda x: x.get("dateTime", x.get("date", "")))
        stmt["cas"].sort(key=lambda x: x.get("dateTime", x.get("reportDate", "")))

    return sorted_stmts


def build_output_xml(statements, output_file):
    """Baut das Ausgabe-XML mit erhaltener FlexStatement-Struktur."""
    filename_without_ext = os.path.splitext(os.path.basename(output_file))[0]

    root = ET.Element("FlexQueryResponse")
    root.set("queryName", filename_without_ext)

    flex_statements_elem = ET.SubElement(root, "FlexStatements", {"count": str(len(statements))})

    for stmt in statements:
        statement = ET.SubElement(flex_statements_elem, "FlexStatement", stmt["attrib"])

        if stmt["trades"]:
            trades_elem = ET.SubElement(statement, "Trades")
            for t in stmt["trades"]:
                ET.SubElement(trades_elem, "Trade", t.attrib)

        if stmt["options"]:
            opt_elem = ET.SubElement(statement, "OptionEAE")
            for o in stmt["options"]:
                opt_elem.append(ET.fromstring(ET.tostring(o)))

        if stmt["cas"]:
            ca_elem = ET.SubElement(statement, "CorporateActions")
            for c in stmt["cas"]:
                ET.SubElement(ca_elem, "CorporateAction", c.attrib)

    xml_str = ET.tostring(root, encoding="unicode")
    pretty_xml = minidom.parseString(xml_str).toprettyxml(indent="  ")
    pretty_lines = [line for line in pretty_xml.split("\n") if line.strip()]

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(pretty_lines))


def main():
    parser = argparse.ArgumentParser(
        description="Extrahiert Einträge für ein Symbol aus allen FlexQuery-XMLs eines Environments"
    )
    parser.add_argument(
        "-t", "--term",
        required=True,
        nargs="+",
        help="underlyingSymbol(e) zum Extrahieren, z.B. -t KO oder -t KO PEP AAPL"
    )
    parser.add_argument(
        "-s", "--source",
        required=True,
        choices=["test", "paper", "money", "autom_money", "autom_paper"],
        help="Environment: test | paper | money | autom_money | autom_paper"
    )

    args = parser.parse_args()
    search_terms = [s.upper() for s in args.term]

    input_files = get_input_files(args.source)
    if not input_files:
        print(f"Keine flex.*.xml Dateien gefunden für Environment '{args.source}'")
        return

    print(f"Lese {len(input_files)} Datei(en) für Environment '{args.source}'...")
    for f in input_files:
        print(f"  {f}")

    statements = collect_by_statement(input_files, search_terms)

    if not statements:
        print(f"Keine Einträge für {search_terms} gefunden.")
        return

    joined = "_".join(search_terms)
    output_file = OUTPUT_DIR / f"flex.{joined}.xml"

    build_output_xml(statements, str(output_file))

    total_trades = sum(len(s["trades"]) for s in statements)
    total_options = sum(len(s["options"]) for s in statements)
    total_cas = sum(len(s["cas"]) for s in statements)

    print(f"\nExtraktion abgeschlossen → {output_file}")
    print(f"  {len(statements)} FlexStatement(s)")
    print(f"  {total_trades} Trades")
    print(f"  {total_options} OptionEAE")
    print(f"  {total_cas} CorporateActions")


if __name__ == "__main__":
    main()
