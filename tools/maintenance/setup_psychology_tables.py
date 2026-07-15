# tools/maintenance/setup_psychology_tables.py
#
# Erstellt die Psychology-Tabellen (4 neue) und droppt die alten V1-Tabellen
# (trade_tag_pivot, trade_notes). Bestehende Trade-Tabellen werden NICHT berührt.
#
# Reihenfolge:
#   Schritt 1: Alte V1-Tabellen droppen (trade_tag_pivot, trade_notes)
#   Schritt 2: Neue Psychology-Tabellen erstellen (DROP IF EXISTS + CREATE)
#   Schritt 3: Default Credit-Spread-Regelwerk seeden
#
# Beispiel:
#   .venv\Scripts\python.exe tools/maintenance/setup_psychology_tables.py money mike_
#   .venv\Scripts\python.exe tools/maintenance/setup_psychology_tables.py paper mike_

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))

from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

from src.config import DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_MAP, TABLE_PREFIX, get_db_url
from src.logger_setup import setup_logging
from src.utils.path_utils import get_project_root
from tools.maintenance.seed_psychology_rulesets import seed_rulesets, RULESETS


def apply_table_prefix(sql_text: str, table_prefix: str) -> str:
    if table_prefix:
        return sql_text.replace("__PREFIX__", table_prefix)
    return sql_text.replace("__PREFIX__", "")


def _prefixed(name: str, prefix: str) -> str:
    return f"{prefix}{name}" if prefix else name


def drop_legacy_tables(conn, table_prefix: str, logger):
    """Schritt 1: Alte V1-Tabellen (Tags/Notes) droppen."""
    legacy = ["trade_tag_pivot", "trade_notes"]
    for table in legacy:
        full = _prefixed(table, table_prefix)
        try:
            conn.execute(text(f"DROP TABLE IF EXISTS `{full}`"))
            logger.info(f"  DROP TABLE IF EXISTS {full}")
        except Exception as e:
            logger.warning(f"  Fehler beim Droppen von {full}: {e}")


def create_psychology_tables(conn, table_prefix: str, logger):
    """Schritt 2: Psychology-Tabellen aus SQL-Dateien erstellen."""
    sql_files = [
        'psychology_rulesets',
        'psychology_rules',
        'psychology_entries',
        'psychology_compliance_results',
    ]
    SQL_PATH = get_project_root() / "sql"

    for sql_file in sql_files:
        file_path = SQL_PATH / f"{sql_file}.sql"
        if not file_path.exists():
            logger.warning(f"  SQL-Datei nicht gefunden: {file_path}")
            continue

        with open(file_path, "r", encoding="utf-8") as f:
            raw_sql = f.read()

        sql_with_prefix = apply_table_prefix(raw_sql, table_prefix)

        for cmd in sql_with_prefix.split(";"):
            cmd = cmd.strip()
            if cmd:
                try:
                    conn.execute(text(cmd))
                except ProgrammingError as e:
                    logger.warning(f"  Fehler in {sql_file}.sql: {e}")

        logger.info(f"  Tabelle erstellt: {_prefixed(sql_file, table_prefix)}")


def seed_default_ruleset(conn, table_prefix: str, environment: str, logger):
    """Schritt 3: Default Credit-Spread-Regelwerk mit 4 Regeln einfügen."""
    rulesets_table = _prefixed("psychology_rulesets", table_prefix)
    rules_table    = _prefixed("psychology_rules",    table_prefix)

    # Prüfen ob schon Daten vorhanden (idempotent)
    existing = conn.execute(
        text(f"SELECT COUNT(*) FROM `{rulesets_table}` WHERE environment = :env"),
        {"env": environment}
    ).scalar()

    if existing > 0:
        logger.info(f"  Seed übersprungen — bereits {existing} Regelwerk(e) für {environment} vorhanden")
        return

    # Ruleset einfügen
    result = conn.execute(
        text(f"""
            INSERT INTO `{rulesets_table}`
                (name, strategy_type, description, is_active, sort_order, environment)
            VALUES
                (:name, :strategy_type, :description, 1, 0, :env)
        """),
        {
            "name":          "Credit Spread Basis",
            "strategy_type": "Credit Spread",
            "description":   "Grundregeln für diszipliniertes Credit-Spread-Trading",
            "env":           environment,
        }
    )
    ruleset_id = result.lastrowid

    # Regeln einfügen
    default_rules = [
        ("tp_50",       "TP bei 50% einhalten",            "Take Profit bei 50% der Prämie schließen, nicht auf mehr warten",         "discipline", 0),
        ("no_fear_exit","Fear-Exit vermeiden",              "Position nicht aus Angst frühzeitig schließen, wenn Plan noch intakt ist", "fear",       1),
        ("stop_respect","Stop-Loss respektieren",           "Stop bei 2x Prämie akzeptieren — nicht hoffen und halten",                "hope",       2),
        ("no_leg_exit", "Kein impulsiver Leg-Exit",         "Einzelne Legs nicht aus Ungeduld vorzeitig schließen",                    "impulse",    3),
    ]

    for rule_key, label, description, error_type, sort_order in default_rules:
        conn.execute(
            text(f"""
                INSERT INTO `{rules_table}`
                    (ruleset_id, rule_key, label, description, error_type, sort_order)
                VALUES
                    (:ruleset_id, :rule_key, :label, :description, :error_type, :sort_order)
            """),
            {
                "ruleset_id":  ruleset_id,
                "rule_key":    rule_key,
                "label":       label,
                "description": description,
                "error_type":  error_type,
                "sort_order":  sort_order,
            }
        )

    logger.info(f"  Seed: Regelwerk '{ruleset_id}' + {len(default_rules)} Regeln für {environment}")


def main():
    if len(sys.argv) < 2:
        print("Verwendung: python setup_psychology_tables.py <environment> [table_prefix]")
        print("Beispiel:   python setup_psychology_tables.py money mike_")
        print(f"Erlaubte Environments: {list(DB_MAP.keys())}")
        sys.exit(1)

    env = sys.argv[1].lower()
    if env not in DB_MAP:
        print(f"Unbekanntes Environment '{env}'. Erlaubt: {list(DB_MAP.keys())}")
        sys.exit(1)

    table_prefix = sys.argv[2] if len(sys.argv) >= 3 else TABLE_PREFIX
    env_up = env.upper()

    log_file = get_project_root() / "log/app.log"
    logger, _ = setup_logging("setup_psychology", level="simple", log_file=log_file)

    print()
    print("=" * 65)
    print("  SETUP PSYCHOLOGY TABLES")
    print("=" * 65)
    print(f"  Environment:  {env_up}")
    print(f"  Prefix:       '{table_prefix}'")
    print(f"  Datenbank:    {DB_MAP[env]}")
    print("=" * 65)

    db_url = get_db_url(env)
    engine = create_engine(db_url)

    with engine.begin() as conn:
        print("\n  Schritt 1: Alte V1-Tabellen droppen...")
        drop_legacy_tables(conn, table_prefix, logger)

        print("\n  Schritt 2: Psychology-Tabellen erstellen...")
        create_psychology_tables(conn, table_prefix, logger)

        print("\n  Schritt 3: Default Credit-Spread-Regelwerk seeden...")
        seed_default_ruleset(conn, table_prefix, env_up, logger)

        print(f"\n  Schritt 4: {len(RULESETS)} Default-Regelwerke seeden...")
        inserted = seed_rulesets(conn, table_prefix, env_up, logger)
        logger.info(f"  {inserted} neue Regelwerk(e) angelegt")

    print()
    print(f"  Fertig! Psychology-Setup fuer {env_up} abgeschlossen.")
    print()


if __name__ == "__main__":
    main()
