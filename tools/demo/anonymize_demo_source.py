# tools/demo/anonymize_demo_source.py
#
# Anonymisiert eine kuratierte Auswahl echter FlexQuery-Testdateien fuer die
# oeffentliche TradingJournal-Demo: ersetzt jede echte accountId durch eine
# feste Fake-ID. Datumswerte bleiben unveraendert (Nutzerentscheidung).
# Basiswerte aus EXCLUDE_UNDERLYINGS werden komplett entfernt.
#
# Optional: --examples <Sammeldatei.xml> zieht zusaetzlich die Kampagnen aus
# EXAMPLE_CAMPAIGNS (Trades, Options-Ereignisse, Kapitalmassnahmen je Basiswert
# und Zeitfenster) aus einer Summary-XML und legt sie als eigene Quelldatei ab.
# Siehe tools/demo/README.md fuer den vollstaendigen Ablauf.

import argparse
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # TradingJournal-Weaver/ in sys.path

from src.utils.path_utils import get_project_root

FAKE_ACCOUNT_ID = "DU0009999"

# Kuratierte Auswahl (~21 von 64 Testdateien) — einzigartige Szenarien laut
# Katalogisierung, Duplikate/Teilmengen bewusst weggelassen.
SOURCE_FILES = [
    # Splits
    "input/test/xflex.APDN_Split.xml",
    "input/test/processed/xflex.CYN_Split.xml",
    "input/test/processed/xflex.TQQ-Split.xml",
    # Assignments
    "input/test/processed/xflex.SPY_Assigned.xml",
    "input/test/xflex.SPX-Ass-CashSet.xml",
    # Vertical Spreads
    "input/test/processed/flex.SPY-VerticalSpread-Exp.xml",
    "input/test/processed/flex.SPY-VerticalSpread-Close.xml",
    "input/test/processed/flex.SPY-VerticalSpread-Aggr-Exp.xml",
    "input/test/processed/xflex.GE-VerticalSpreads.xml",
    "input/test/processed/flex.CLS-VerticalSpread-Exp.xml",
    # Wheel-Strategie
    "input/test/processed/xflex.ON_wheel.xml",
    # Partial Fills / BookTrade-Zuordnung (volle Historie statt isolierter
    # Tages-Ausschnitte — OMEX_1/2/3 wurden verworfen: sie setzen frueheren
    # Bestand voraus, der ohne die vorangehende Historie fehlt und beim
    # BookTrade-Matching zu Zeilen ohne dateTime fuehrt, siehe README)
    "input/test/flex.OMEX.xml",
    # Cash-Settlement
    "input/test/processed/SPY_SPX_all.xml",
    # Großer realer Kontoauszug (mehrere Symbole, ein Monat)
    "input/flex/flex.1116666.paper_30_report.20250818.20250916.xml",
    # Closing-Trades fuer die SPY-Zuteilung aus xflex.SPY_Assigned.xml (23.09.2025,
    # 700 Stk @ 664): ohne diese Datei bleibt die daraus resultierende Aktienposition
    # in der Demo dauerhaft offen (4 Verkaeufe -29/-71/-100/-500 = 700, verteilt auf
    # 25.09.-01.10.2025)
    "input/test/processed/flex.1116666.paper_30_report.20250922.20251020.xml",
    # Verfalls-Ereignisse fuer sonst dauerhaft "offen" bleibende, kalendarisch laengst
    # verfallene Optionspositionen (2026-08-14 gefunden: OpenOptions filtert nur nach
    # processed=0, nicht nach Expiry-Datum) — je Datei die enthaltenen Expirations:
    #   20250901.20250929 -> ON 250919C00053000
    #   20251001.20251030 -> GE 251024P00282500/287500, CLS 251024P00235-250000 (2 Spreads)
    #   20251120.20251219 -> SPX 251121 Iron Condor (4 Legs)
    "input/test/processed/xflex.1116666.paper_30_report.20250901.20250929.xml",
    "input/test/processed/flex.1116666.paper_30_report.20251001.20251030.xml",
    "input/test/processed/flex.1116666.paper_30_report.20251120.20251219.xml",
    # Sonstige/Vielfalt
    "input/test/xflex.FULC.xml",
    "input/test/processed/xflex.Cash.xml",
    "input/test/processed/flex.HIMS.xml",
    "input/test/processed/flex.MATV.xml",
    "input/test/processed/flex.SOUN.xml",
]

# Basiswerte, die in der Demo gar nicht vorkommen sollen (alle Elemente entfernt)
EXCLUDE_UNDERLYINGS = {"TLT"}

# Abgeschlossene Kampagnen 2026 fuer --examples: (Basiswert, erster Tag, letzter Tag).
# Nur Kampagnen, die nach dem letzten Trade der SOURCE_FILES (10.02.2026) beginnen und
# deren Basiswert dort nicht mehr offen ist - sonst mischen sie sich mit Demo-Bestand.
EXAMPLE_CAMPAIGNS = [
    ("ORCL", "2026-02-20", "2026-03-05"),
    ("USO", "2026-02-26", "2026-03-06"),
    ("SOFI", "2026-03-05", "2026-03-09"),
    ("EEM", "2026-03-10", "2026-03-13"),
    ("CAT", "2026-03-10", "2026-03-24"),
    ("ALB", "2026-03-19", "2026-03-24"),
    ("EEM", "2026-04-09", "2026-04-14"),
    ("LRCX", "2026-04-09", "2026-04-10"),
    ("MARA", "2026-04-10", "2026-04-17"),
    ("JBHT", "2026-04-17", "2026-04-20"),
    ("COIN", "2026-04-21", "2026-05-04"),
    ("GE", "2026-05-06", "2026-05-26"),
    ("LRCX", "2026-05-06", "2026-05-22"),
    ("XYL", "2026-05-28", "2026-06-15"),
    ("RBLX", "2026-06-15", "2026-06-16"),
    ("AMD", "2026-06-15", "2026-07-14"),
    ("TXN", "2026-06-22", "2026-07-29"),
    ("PG", "2026-07-02", "2026-07-27"),
    ("GS", "2026-07-22", "2026-08-21"),
    ("CRWD", "2026-07-22", "2026-08-10"),
    ("USO", "2026-07-23", "2026-08-06"),
    ("CRDO", "2026-08-05", "2026-08-07"),
    ("CSCO", "2026-08-05", "2026-08-21"),
    ("TXN", "2026-08-18", "2026-09-01"),
    ("CSCO", "2026-09-03", "2026-09-22"),
    ("NKE", "2026-09-03", "2026-09-18"),
]
EXAMPLES_FILENAME = "flex.examples_2026.xml"

OUTPUT_DIR = get_project_root() / "input" / "demo_source"


def underlying_of(elem: ET.Element) -> str:
    """Basiswert eines Trade/OptionEAE/CorporateAction-Elements ('' wenn keiner)."""
    return elem.get("underlyingSymbol") or (elem.get("symbol") or "").split(" ")[0]


def date_of(elem: ET.Element) -> date | None:
    """Datum eines Elements aus tradeDate/date/reportDate (IBKR-Format TT/MM/JJJJ)."""
    for attr in ("tradeDate", "date", "reportDate"):
        value = elem.get(attr)
        if value:
            return datetime.strptime(value.split(";")[0], "%d/%m/%Y").date()
    return None


def filter_statements(root: ET.Element, keep) -> int:
    """
    Entfernt in allen FlexStatements jedes Eintrags-Element (Kinder von Trades,
    OptionEAE, CorporateActions ...), fuer das keep(elem) False liefert. Danach leere
    FlexStatements ebenfalls. Gibt die Zahl der behaltenen Eintraege zurueck.
    """
    kept = 0
    for container in root.iter("FlexStatements"):
        for stmt in list(container):
            for section in stmt:
                for entry in list(section):
                    if keep(entry):
                        kept += 1
                    else:
                        section.remove(entry)
            if not any(len(section) for section in stmt):
                container.remove(stmt)
    return kept


def not_excluded(elem: ET.Element) -> bool:
    return underlying_of(elem) not in EXCLUDE_UNDERLYINGS


def in_example_campaign(elem: ET.Element) -> bool:
    symbol, day = underlying_of(elem), date_of(elem)
    if day is None:
        return False
    return any(symbol == sym and date.fromisoformat(start) <= day <= date.fromisoformat(end)
               for sym, start, end in EXAMPLE_CAMPAIGNS)


def demo_filename(src_name: str) -> str:
    """
    TEST-Modus-Import (import_ibkr_trades.py) pickt nur Dateien, deren Name mit
    'flex.' beginnt (siehe _import_xml_to_test). Normalisiert daher jeden
    Dateinamen auf 'flex.<rest>.xml', unabhaengig vom urspruenglichen
    flex./xflex.-Praefix oder Namen ganz ohne Praefix.
    """
    stem = src_name
    for prefix in ("xflex.", "flex."):
        if stem.lower().startswith(prefix):
            stem = stem[len(prefix):]
            break
    return f"flex.{stem}"


def anonymize_file(src_path: Path, dest_path: Path, keep=not_excluded) -> int:
    """
    Kopiert eine FlexQuery-XML-Datei, entfernt alle Eintraege, fuer die keep()
    False liefert (Standard: Basiswerte aus EXCLUDE_UNDERLYINGS), und ersetzt jedes
    accountId-Attribut (auf jeder Elementebene, nicht nur FlexStatement) durch die
    Fake-ID. Gibt die Anzahl ersetzter Attribute zurueck.
    """
    tree = ET.parse(src_path)
    root = tree.getroot()
    filter_statements(root, keep)

    replaced = 0
    for elem in root.iter():
        if "accountId" in elem.attrib:
            elem.set("accountId", FAKE_ACCOUNT_ID)
            replaced += 1

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(dest_path, encoding="UTF-8", xml_declaration=True)
    return replaced


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo-Quelldateien anonymisieren")
    parser.add_argument("--examples", type=Path, metavar="SUMMARY_XML",
                        help="Summary-XML, aus der die EXAMPLE_CAMPAIGNS gezogen werden")
    args = parser.parse_args()

    project_root = get_project_root()
    total_replaced = 0
    total_size = 0
    missing = []

    for rel_path in SOURCE_FILES:
        src_path = project_root / rel_path
        if not src_path.exists():
            missing.append(rel_path)
            continue

        dest_path = OUTPUT_DIR / demo_filename(src_path.name)
        replaced = anonymize_file(src_path, dest_path)
        total_replaced += replaced
        total_size += dest_path.stat().st_size
        print(f"  {src_path.name}: {replaced} accountId-Attribut(e) ersetzt")

    if args.examples:
        dest_path = OUTPUT_DIR / EXAMPLES_FILENAME
        replaced = anonymize_file(args.examples, dest_path,
                                  keep=lambda e: not_excluded(e) and in_example_campaign(e))
        kept = sum(len(section) for section in ET.parse(dest_path).getroot().iter()
                   if section.tag in ("Trades", "OptionEAE", "CorporateActions"))
        total_replaced += replaced
        print(f"  {EXAMPLES_FILENAME}: {kept} Eintraege aus {len(EXAMPLE_CAMPAIGNS)} Kampagnen, "
              f"{replaced} accountId-Attribut(e) ersetzt")

    print()
    print(f"{len(SOURCE_FILES) - len(missing)}/{len(SOURCE_FILES)} Dateien anonymisiert "
          f"-> {OUTPUT_DIR}")
    print(f"Gesamtgröße: {total_size / 1024:.0f} KB, {total_replaced} accountId-Ersetzungen gesamt")

    if missing:
        print()
        print("FEHLEND (nicht gefunden, übersprungen):")
        for rel_path in missing:
            print(f"  - {rel_path}")


if __name__ == "__main__":
    main()
