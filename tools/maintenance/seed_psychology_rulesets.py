# tools/maintenance/seed_psychology_rulesets.py
#
# Fügt vordefinierte Psychology-Regelwerke in die DB ein (idempotent).
# Bereits vorhandene Regelwerke (gleicher Name + Environment) werden übersprungen.
#
# Regelwerke:
#   - Aktien Long (Kauf)           — Entry-Disziplin
#   - Aktien Exit (Verkauf/Close)  — Exit-Disziplin
#   - Short Put / CSP              — Put-Verkäufer
#   - Short Call / Covered Call    — Call-Verkäufer
#   - Iron Condor                  — Beide Seiten
#
# Verwendung:
#   .venv\Scripts\python.exe tools/maintenance/seed_psychology_rulesets.py money mike_
#   .venv\Scripts\python.exe tools/maintenance/seed_psychology_rulesets.py paper mike_

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))

from sqlalchemy import create_engine, text

from src.config import DB_MAP, TABLE_PREFIX, get_db_url, TABLE_PSYCHOLOGY_RULESETS, TABLE_PSYCHOLOGY_RULES
from src.logger_setup import setup_logging
from src.utils.path_utils import get_project_root


def _prefixed(name: str, prefix: str) -> str:
    return f"{prefix}{name}" if prefix else name


# ── Regelwerk-Definitionen ───────────────────────────────────────────────────
#
# Format pro Regelwerk:
#   (name, strategy_type, description, sort_order, [
#       (rule_key, label, description, error_type, sort_order),
#       ...
#   ])

RULESETS = [
    (
        "Aktien Long (Kauf)",
        "Aktien Long",
        "Entry-Disziplin beim Kaufen von Aktien",
        10,
        [
            ("system_entry",    "System-Signal bestätigt",          "Entry nur wenn Regelwerk-Kriterien erfüllt — kein FOMO-Einstieg",           "impulse",    0),
            ("position_sizing", "Position-Sizing eingehalten",       "Max. erlaubte Positionsgröße nicht überschritten",                           "greed",      1),
            ("stop_defined",    "Stop-Loss vor Entry definiert",     "Expliziter Stop-Kurs notiert, nicht 'irgendwo darunter'",                    "discipline", 2),
            ("no_chasing",      "Kein Chasing nach großem Move",     "Nicht in einen bereits stark gestiegenen Kurs einsteigen",                   "impulse",    3),
            ("no_news_entry",   "Kein Entry direkt vor Earnings",    "Erhöhtes Gap-Risiko gemieden — kein Trade kurz vor Earnings/News",           "discipline", 4),
        ]
    ),
    (
        "Aktien Exit (Verkauf)",
        "Aktien Exit",
        "Exit-Disziplin beim Schließen von Aktien-Positionen",
        20,
        [
            ("stop_no_hesitation", "Stop-Loss ohne Zögern ausgeführt",  "Kein 'kurz noch warten' wenn Stop getriggert wurde",                    "fear",       0),
            ("no_hope_hold",       "Kein Halten aus Hoffnung",           "Wenn der Plan sagt Exit — dann Exit, nicht auf Erholung hoffen",        "hope",       1),
            ("no_panic_sell",      "Kein Panic-Sell bei normaler Vola",  "Normale Schwankungen nicht als Exit-Signal missdeuten",                 "fear",       2),
            ("tp_respected",       "Gewinnziel eingehalten",             "TP-Kurs war vor Entry definiert und wurde respektiert",                 "greed",      3),
            ("no_revenge_add",     "Keine Positionserweiterung nach Verlust", "Verlierenden Trade nicht verdoppeln aus Revenge-Trading",          "greed",      4),
        ]
    ),
    (
        "Short Put / CSP",
        "Short Put",
        "Regeln für das Verkaufen von Puts (Cash-Secured oder im Spread)",
        30,
        [
            ("tp_50",          "TP bei 50% der Prämie",           "Position schließen wenn 50% Gewinn erreicht — nicht auf mehr warten",     "greed",      0),
            ("strike_selection","Strike klar OTM gewählt",          "Nicht zu nah am Geld aus Gier nach mehr Prämie",                          "greed",      1),
            ("no_fear_exit",   "Kein frühzeitiger Fear-Exit",      "Position nicht aus Angst schließen solange der Plan noch intakt ist",      "fear",       2),
            ("dte_stop",       "DTE-Stop respektiert (≤ 21 DTE)",  "Position spätestens bei 21 DTE schließen (erhöhtes Gamma-Risiko)",         "discipline", 3),
            ("no_hope_roll",   "Kein Roll aus Hoffnung",           "Nur rollen wenn es einen klaren Vorteil bringt — nicht um Verlust zu verschieben", "hope", 4),
        ]
    ),
    (
        "Short Call / Covered Call",
        "Short Call",
        "Regeln für das Verkaufen von Calls (gedeckt oder als Strategie-Leg)",
        40,
        [
            ("covered_confirmed",   "Position ist gedeckt",                  "Underlying-Position vorhanden (Covered Call) — kein Naked Call aus Versehen",  "discipline", 0),
            ("tp_50",               "TP bei 50% der Prämie",                 "Position schließen wenn 50% Gewinn erreicht",                                   "greed",      1),
            ("no_impulse_buyback",  "Kein Impuls-Rückkauf bei steigendem Call", "Nicht aus Angst vor weiter steigendem Kurs impulsiv covern",                "impulse",    2),
            ("assignment_accepted", "Assignment als Plan akzeptiert",         "Wenn Aktie assigned wird: das war Teil des Plans — kein Panic-Buyback",        "fear",       3),
            ("no_roll_hope",        "Kein Roll nur zur Assignment-Vermeidung","Rollen nur wenn Strike + Prämie strategisch sinnvoll — nicht aus Angst",       "hope",       4),
        ]
    ),
    (
        "Iron Condor",
        "Iron Condor",
        "Diszipliniertes Management beider Seiten eines Iron Condors",
        50,
        [
            ("tp_25_50",            "TP bei 25–50% des Max-Credits",         "Iron Condor früh schließen — nicht auf den vollen Credit warten",              "greed",      0),
            ("both_sides_checked",  "Beide Seiten vor Entry analysiert",     "Strike-Wahl auf Call- und Put-Seite nach System, nicht nur eine Seite",        "discipline", 1),
            ("no_one_sided_panic",  "Keine einseitige Panik-Schließung",     "Nicht nur eine Seite aus Angst schließen — Gesamtposition und Delta bedenken", "fear",       2),
            ("adjust_not_hope",     "Anpassen statt Hoffen bei Bedrohung",  "Wenn eine Seite bedroht ist: anpassen oder schließen — nicht hoffen",           "hope",       3),
            ("size_respected",      "Position-Sizing respektiert",           "Nicht mehr Kontrakte als bei normalen Spreads wegen vermeintlich geringem Risiko", "greed",   4),
        ]
    ),
]


def seed_rulesets(conn, table_prefix: str, environment: str, logger) -> int:
    """Fügt alle Regelwerke idempotent ein. Gibt Anzahl neu angelegter Rulesets zurück."""
    rulesets_table = _prefixed(TABLE_PSYCHOLOGY_RULESETS, table_prefix)
    rules_table    = _prefixed(TABLE_PSYCHOLOGY_RULES,    table_prefix)

    inserted = 0

    for name, strategy_type, description, sort_order, rules in RULESETS:
        # Prüfen ob dieses Regelwerk (per Name + Environment) schon existiert
        existing_id = conn.execute(
            text(f"SELECT id FROM `{rulesets_table}` WHERE name = :name AND environment = :env LIMIT 1"),
            {"name": name, "env": environment}
        ).scalar()

        if existing_id:
            logger.info(f"  Übersprungen (bereits vorhanden): '{name}' [{environment}]")
            continue

        # Ruleset einfügen
        result = conn.execute(
            text(f"""
                INSERT INTO `{rulesets_table}`
                    (name, strategy_type, description, is_active, sort_order, environment)
                VALUES
                    (:name, :strategy_type, :description, 1, :sort_order, :env)
            """),
            {
                "name":          name,
                "strategy_type": strategy_type,
                "description":   description,
                "sort_order":    sort_order,
                "env":           environment,
            }
        )
        ruleset_id = result.lastrowid

        # Regeln einfügen
        for rule_key, label, rule_desc, error_type, rule_order in rules:
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
                    "description": rule_desc,
                    "error_type":  error_type,
                    "sort_order":  rule_order,
                }
            )

        logger.info(f"  Eingefügt: '{name}' (ID {ruleset_id}) mit {len(rules)} Regeln [{environment}]")
        inserted += 1

    return inserted


def main():
    if len(sys.argv) < 2:
        print("Verwendung: python seed_psychology_rulesets.py <environment> [table_prefix]")
        print("Beispiel:   python seed_psychology_rulesets.py money mike_")
        print(f"Erlaubte Environments: {list(DB_MAP.keys())}")
        sys.exit(1)

    env = sys.argv[1].lower()
    if env not in DB_MAP:
        print(f"Unbekanntes Environment '{env}'. Erlaubt: {list(DB_MAP.keys())}")
        sys.exit(1)

    table_prefix = sys.argv[2] if len(sys.argv) >= 3 else TABLE_PREFIX
    env_up = env.upper()

    log_file = get_project_root() / "log/app.log"
    logger, _ = setup_logging("seed_psychology", level="simple", log_file=log_file)

    print()
    print("=" * 65)
    print("  SEED PSYCHOLOGY RULESETS")
    print("=" * 65)
    print(f"  Environment:  {env_up}")
    print(f"  Prefix:       '{table_prefix}'")
    print(f"  Datenbank:    {DB_MAP[env]}")
    print(f"  Regelwerke:   {len(RULESETS)}")
    print("=" * 65)

    db_url = get_db_url(env)
    engine = create_engine(db_url)

    with engine.begin() as conn:
        inserted = seed_rulesets(conn, table_prefix, env_up, logger)

    print()
    print(f"  Fertig! {inserted} neue Regelwerk(e) für {env_up} angelegt.")
    print(f"  (Bereits vorhandene wurden übersprungen.)")
    print()


if __name__ == "__main__":
    main()
