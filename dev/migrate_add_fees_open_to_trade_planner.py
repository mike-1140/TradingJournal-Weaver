"""
Migration: fees_open in trade_planner nachruesten
====================================================
Fuegt die Spalte `fees_open` (Kommission bei Eroeffnung, analog zu fees_close)
zu `trade_planner` hinzu, falls noch nicht vorhanden. Bei Options-Trades wird
die Eroeffnungskommission bereits pro Leg in trade_planner_legs.fees erfasst —
fees_open schliesst die Luecke fuer Aktien-Trades ohne Legs.

Aufruf:
  python src/migrate_add_fees_open_to_trade_planner.py               # alle aktiven Targets aus pipeline.toml
  python src/migrate_add_fees_open_to_trade_planner.py money mike_   # einzelnes Target
"""

import sys
from sqlalchemy import text
from src.config import get_engine, load_active_targets, TABLE_TRADE_PLANNER
from src.logger_setup import setup_logging


def _prefixed(prefix: str, table: str) -> str:
    return f"{prefix}{table}" if prefix else table


def _add_column_if_missing(conn, table: str) -> None:
    result = conn.execute(text(f"SHOW COLUMNS FROM `{table}` LIKE 'fees_open'"))
    if result.first():
        print("  [OK]  Spalte 'fees_open' bereits vorhanden")
        return

    conn.execute(text(
        f"ALTER TABLE `{table}` ADD COLUMN `fees_open` DECIMAL(10,2) DEFAULT NULL "
        f"COMMENT 'Kommission bei Eroeffnung (v.a. Aktien-Trades ohne Legs)' AFTER `price_open`"
    ))
    print("  [NEU] Spalte 'fees_open' hinzugefuegt")


def migrate_target(environment: str, prefix: str, logger) -> None:
    logger.info(f"[{environment.upper()} / prefix='{prefix}'] Starte Migration ...")
    table = _prefixed(prefix, TABLE_TRADE_PLANNER)

    engine = get_engine(environment)
    with engine.begin() as conn:
        print(f"\n  Tabelle: {table}")
        _add_column_if_missing(conn, table)
        logger.info(f"[{environment.upper()}] Migration abgeschlossen")


def main():
    logger, _ = setup_logging("migrate_add_fees_open_to_trade_planner")

    if len(sys.argv) == 3:
        targets = [{"environment": sys.argv[1], "prefix": sys.argv[2]}]
    else:
        targets = load_active_targets()
        if not targets:
            logger.error("Keine aktiven Targets in pipeline.toml gefunden.")
            sys.exit(1)

    print(f"\n=== fees_open-Migration ({len(targets)} Target(s)) ===\n")
    for t in targets:
        try:
            migrate_target(t["environment"], t["prefix"], logger)
        except Exception as e:
            logger.error(f"Fehler bei {t['environment']}/{t['prefix']}: {e}")
            raise

    print("\n=== Migration abgeschlossen ===\n")


if __name__ == "__main__":
    main()
