# tools/demo/anonymize_demo_source.py
#
# Anonymisiert eine kuratierte Auswahl echter FlexQuery-Testdateien fuer die
# oeffentliche TradingJournal-Demo: ersetzt jede echte accountId durch eine
# feste Fake-ID. Datumswerte bleiben unveraendert (Nutzerentscheidung).
# Siehe tools/demo/README.md fuer den vollstaendigen Ablauf.

import sys
import xml.etree.ElementTree as ET
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

OUTPUT_DIR = get_project_root() / "input" / "demo_source"


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


def anonymize_file(src_path: Path, dest_path: Path) -> int:
    """
    Kopiert eine FlexQuery-XML-Datei und ersetzt jedes accountId-Attribut
    (auf jeder Elementebene, nicht nur FlexStatement) durch die Fake-ID.
    Gibt die Anzahl ersetzter Attribute zurueck.
    """
    tree = ET.parse(src_path)
    root = tree.getroot()

    replaced = 0
    for elem in root.iter():
        if "accountId" in elem.attrib:
            elem.set("accountId", FAKE_ACCOUNT_ID)
            replaced += 1

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(dest_path, encoding="UTF-8", xml_declaration=True)
    return replaced


def main() -> None:
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
