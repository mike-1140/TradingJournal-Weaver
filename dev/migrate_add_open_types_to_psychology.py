"""
Migration: 'open'/'open_spread' als trade_type in psychology_entries zulassen
==============================================================================
Erweitert das ENUM `trade_type` von ('closed','spread') auf ('open','closed',
'open_spread','spread'), damit Psychology-Einträge auch beim Eröffnen eines
Trades (nicht nur beim Schließen) erfasst werden können. Rein additiv (MODIFY
COLUMN mit erweitertem ENUM) — bestehende Werte 'closed'/'spread' bleiben gültig.

Aufruf:
  python src/migrate_add_open_types_to_psychology.py               # alle aktiven Targets aus pipeline.toml
  python src/migrate_add_open_types_to_psychology.py money mike_    # einzelnes Target
"""

import sys
from sqlalchemy import text
from src.config import get_engine, load_active_targets, TABLE_PSYCHOLOGY_ENTRIES
from src.logger_setup import setup_logging


def _prefixed(prefix: str, table: str) -> str:
    return f"{prefix}{table}" if prefix else table


def _widen_enum_if_needed(conn, table: str) -> None:
    exists = conn.execute(text(f"SHOW TABLES LIKE '{table}'")).first()
    if exists is None:
        print(f"  [SKIP] Tabelle {table} existiert nicht (Psychology-Modul hier nicht eingerichtet)")
        return

    result = conn.execute(text(f"SHOW COLUMNS FROM `{table}` LIKE 'trade_type'"))
    row = result.first()
    if row is None:
        print(f"  [WARN] Spalte 'trade_type' nicht gefunden in {table}, uebersprungen")
        return

    current_type = row[1]  # z.B. "enum('closed','spread')"
    if "'open'" in current_type and "'open_spread'" in current_type:
        print("  [OK]  ENUM enthaelt bereits 'open'/'open_spread'")
        return

    conn.execute(text(
        f"ALTER TABLE `{table}` MODIFY COLUMN `trade_type` "
        f"ENUM('open','closed','open_spread','spread') DEFAULT NULL"
    ))
    print("  [NEU] ENUM auf ('open','closed','open_spread','spread') erweitert")


def migrate_target(environment: str, prefix: str, logger) -> None:
    logger.info(f"[{environment.upper()} / prefix='{prefix}'] Starte Migration ...")
    table = _prefixed(prefix, TABLE_PSYCHOLOGY_ENTRIES)

    engine = get_engine(environment)
    with engine.begin() as conn:
        print(f"\n  Tabelle: {table}")
        _widen_enum_if_needed(conn, table)
        logger.info(f"[{environment.upper()}] Migration abgeschlossen")


def main():
    logger, _ = setup_logging("migrate_add_open_types_to_psychology")

    if len(sys.argv) == 3:
        targets = [{"environment": sys.argv[1], "prefix": sys.argv[2]}]
    else:
        targets = load_active_targets()
        if not targets:
            logger.error("Keine aktiven Targets in pipeline.toml gefunden.")
            sys.exit(1)

    print(f"\n=== trade_type-ENUM-Migration ({len(targets)} Target(s)) ===\n")
    for t in targets:
        try:
            migrate_target(t["environment"], t["prefix"], logger)
        except Exception as e:
            logger.error(f"Fehler bei {t['environment']}/{t['prefix']}: {e}")
            raise

    print("\n=== Migration abgeschlossen ===\n")


if __name__ == "__main__":
    main()
