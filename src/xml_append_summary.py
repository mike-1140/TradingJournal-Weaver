# src/xml_append_summary.py
# Erstellt/aktualisiert summary.xml aus den bereits verarbeiteten flex.*.xml-Dateien in processed/.
# Keine Duplikate (fromDate eindeutig), aufsteigende Reihenfolge, Performance-Cache.

import json
import sys
from pathlib import Path
import xml.etree.ElementTree as ET
import xml.dom.minidom
from datetime import datetime
from pathlib import Path

from src.config import DB_MAP, load_active_targets
from src.logger_setup import setup_logging
from src.utils.path_utils import get_project_root

# Konstanten – analog zu import_ibkr_trades.py
BASE_XML_FILE_PATH_PROD = r'C:\Trade_XML'

FLEX_FILE_PREFIX = "flex."
# Dateinamen werden dynamisch aus table_prefix + environment gebildet:
# summary_{table_prefix}{environment}.xml  z.B. summary_mike_money.xml
# summary_{table_prefix}{environment}_cache.json

# Logging
log_file = get_project_root() / "log/app.log"
logger, _ = setup_logging('my_app', level="simple", log_file=log_file)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def parse_date(date_str: str) -> datetime:
    """Wandelt fromDate (DD/MM/YYYY oder YYYYMMDD) in datetime-Objekt um."""
    for fmt in ("%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            pass
    raise ValueError(f"Unbekanntes Datumsformat: {date_str!r}")


def prettify_xml(elem: ET.Element) -> str:
    """Erzeugt formatierten XML-String mit Einrückung."""
    rough_string = ET.tostring(elem, encoding="utf-8")
    reparsed = xml.dom.minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")


def is_statement_empty(statement: ET.Element) -> bool:
    """Prüft, ob FlexStatement keine inhaltlichen Kinder mit Daten hat."""
    for child in statement:
        if len(child):
            return False
    return True


# ---------------------------------------------------------------------------
# Cache: verarbeitete Dateinamen merken
# ---------------------------------------------------------------------------

def load_cache(cache_file: Path) -> set:
    """Lädt die Liste bereits verarbeiteter Dateinamen aus dem Cache."""
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return set(data.get("processed_files", []))
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Cache-Datei beschädigt, wird neu erstellt: {e}")
    return set()


def save_cache(cache_file: Path, processed_files: set) -> None:
    """Speichert die Liste verarbeiteter Dateinamen im Cache."""
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump({"processed_files": sorted(processed_files)}, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Summary-XML laden/erstellen/speichern
# ---------------------------------------------------------------------------

def _new_summary():
    """Erstellt leere Summary-Struktur."""
    root  = ET.Element("FlexQueryResponse", {"queryName": "Summary_Report", "type": "AF"})
    stmts = ET.SubElement(root, "FlexStatements", {"count": "0"})
    return root, stmts, set()


def load_summary(summary_file: Path):
    """
    Lädt bestehendes summary.xml.
    Gibt (root, statements_elem, known_from_dates) zurück.
    Erstellt neu, falls nicht vorhanden oder beschädigt.
    """
    if summary_file.exists():
        try:
            tree  = ET.parse(summary_file)
            root  = tree.getroot()
            stmts = root.find("FlexStatements")

            if stmts is None:
                logger.warning("Kein <FlexStatements> in summary.xml – wird neu erstellt")
                return _new_summary()

            known_dates = {
                s.get("fromDate")
                for s in stmts.findall("FlexStatement")
                if s.get("fromDate")
            }
            count = len(stmts.findall("FlexStatement"))
            if known_dates:
                last = max(parse_date(d) for d in known_dates).strftime("%d.%m.%Y")
            else:
                last = "–"
            logger.info(f"Summary geladen: {count} Statements, letztes fromDate: {last}")
            return root, stmts, known_dates

        except ET.ParseError as e:
            logger.error(f"Fehler beim Parsen von summary.xml: {e} – wird neu erstellt")

    logger.info("Kein summary.xml gefunden – wird neu erstellt")
    return _new_summary()


def save_summary(summary_file: Path, root: ET.Element, stmts_elem: ET.Element) -> None:
    """Sortiert alle Statements nach fromDate (aufsteigend) und speichert summary.xml."""
    all_stmts = stmts_elem.findall("FlexStatement")

    # Alle Kinder entfernen
    for s in all_stmts:
        stmts_elem.remove(s)

    # Aufsteigend nach fromDate sortieren
    all_stmts.sort(key=lambda s: parse_date(s.get("fromDate", "01/01/1900")))

    for s in all_stmts:
        stmts_elem.append(s)

    stmts_elem.set("count", str(len(all_stmts)))

    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(prettify_xml(root))

    logger.info(f"Summary gespeichert: {len(all_stmts)} Statements → {summary_file}")


# ---------------------------------------------------------------------------
# Haupt-Logik
# ---------------------------------------------------------------------------

def build_summary(environment: str, table_prefix: str, user: str = "") -> None:
    """
    Liest neue flex.*.xml-Dateien aus processed/ und aktualisiert die account-spezifische Summary.
    Dateiname: summary_{table_prefix}{environment}.xml  z.B. summary_mike_money.xml
    environment: paper | money | autom_money | autom_paper | test
    user: Unterordner in <env>/<user>/processed/ — leer für Legacy-Pfad ohne User-Ebene.
    """
    environment = environment.lower()

    env_dir       = Path(BASE_XML_FILE_PATH_PROD) / environment
    user_dir      = env_dir / user if user else env_dir
    processed_dir = user_dir / "processed"
    summary_file  = env_dir / f"summary_{table_prefix}{environment}.xml"
    cache_file    = env_dir / f"summary_{table_prefix}{environment}_cache.json"

    logger.info("=" * 80)
    logger.info(
        f"Summary-Build: {table_prefix}{environment.upper()} "
        f"({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
    )
    logger.info(f"  Quelle:  {processed_dir}")
    logger.info(f"  Summary: {summary_file}")
    logger.info("=" * 80)

    if not processed_dir.exists():
        logger.warning(f"processed/-Verzeichnis nicht gefunden: {processed_dir}")
        return

    # Cache und bestehendes Summary laden
    already_done           = load_cache(cache_file)
    root, stmts_elem, known_dates = load_summary(summary_file)

    # Alle flex.*.xml in processed/ ermitteln, nur neue (nicht im Cache)
    all_flex_files = sorted(
        f for f in processed_dir.iterdir()
        if f.name.lower().startswith(FLEX_FILE_PREFIX) and f.name.lower().endswith(".xml")
    )
    new_files = [f for f in all_flex_files if f.name not in already_done]

    logger.info(f"Dateien in processed/: {len(all_flex_files)}  davon neu: {len(new_files)}")

    if not new_files:
        logger.info("Keine neuen Dateien – Summary ist aktuell.")
        return

    added_total        = 0
    skipped_duplicate  = 0
    skipped_empty      = 0
    newly_processed    = set()

    for xml_file in new_files:
        logger.info(f"Verarbeite: {xml_file.name}")
        try:
            tree       = ET.parse(xml_file)
            input_root = tree.getroot()
            stmts_in   = input_root.find("FlexStatements")

            if stmts_in is None:
                logger.warning(f"  Kein <FlexStatements> – übersprungen")
                newly_processed.add(xml_file.name)
                continue

            file_added = 0
            for stmt in stmts_in.findall("FlexStatement"):
                from_date_str = stmt.get("fromDate")
                if not from_date_str:
                    continue

                if is_statement_empty(stmt):
                    skipped_empty += 1
                    logger.debug(f"  Leer übersprungen: {from_date_str}")
                    continue

                if from_date_str in known_dates:
                    skipped_duplicate += 1
                    logger.debug(f"  Duplikat übersprungen: {from_date_str}")
                    continue

                # Tiefe Kopie und hinzufügen
                new_stmt = ET.fromstring(ET.tostring(stmt))
                stmts_elem.append(new_stmt)
                known_dates.add(from_date_str)
                added_total += 1
                file_added  += 1

            logger.info(f"  +{file_added} Statements hinzugefügt")
            newly_processed.add(xml_file.name)

        except ET.ParseError as e:
            logger.error(f"  XML-Fehler in {xml_file.name}: {e}")
        except Exception as e:
            logger.error(f"  Fehler bei {xml_file.name}: {e}")

    # Summary speichern (nur wenn sich etwas geändert hat)
    if added_total > 0:
        save_summary(summary_file, root, stmts_elem)
    else:
        logger.info("Keine neuen Statements hinzugefügt – Summary unverändert.")

    # Cache immer aktualisieren (auch bei Duplikaten/leeren Dateien)
    already_done.update(newly_processed)
    save_cache(cache_file, already_done)

    logger.info(
        f"Fertig: +{added_total} Statements, "
        f"{skipped_duplicate} Duplikate übersprungen, "
        f"{skipped_empty} leere übersprungen"
    )


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) >= 3:
        # CLI-Override: explizites Environment + Prefix haben Vorrang
        env    = sys.argv[1].lower()
        prefix = sys.argv[2]
        valid_envs = list(DB_MAP.keys())
        if env not in valid_envs:
            print(f"Ungültiges Environment: {env!r}. Gültig: {', '.join(valid_envs)}")
            sys.exit(1)
        build_summary(env, prefix)
    elif len(sys.argv) == 1:
        # Auto-Modus: alle aktiven Targets aus pipeline.toml — TEST ausgenommen,
        # da Testdaten kein Summary-Replay brauchen (jederzeit neu importierbar)
        targets = [t for t in load_active_targets() if t["environment"] != "test"]
        if not targets:
            print("Keine aktiven Targets in pipeline.toml gefunden.")
            sys.exit(0)
        for t in targets:
            build_summary(t["environment"], t["prefix"], t.get("user", ""))
    else:
        print("Usage: python xml_append_summary.py <environment> <table_prefix>")
        print("  Oder ohne Parameter: alle aktiven Environments aus pipeline.toml")
        sys.exit(1)


if __name__ == "__main__":
    main()
