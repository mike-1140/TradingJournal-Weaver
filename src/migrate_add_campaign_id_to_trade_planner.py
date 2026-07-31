"""
Migration: campaign_id in trade_planner nachrüsten
====================================================
Fügt die Spalte `campaign_id` (nullable FK auf trading_campaigns) zu `trade_planner`
hinzu, falls noch nicht vorhanden. Bestehende Zeilen bleiben unverknüpft (NULL) —
die Verknüpfung erfolgt nachträglich manuell oder per Matching-Vorschlag in TradingJournal2.

Aufruf:
  python src/migrate_add_campaign_id_to_trade_planner.py               # alle aktiven Targets aus pipeline.toml
  python src/migrate_add_campaign_id_to_trade_planner.py money mike_   # einzelnes Target
"""

import sys
from sqlalchemy import text
from src.config import get_engine, load_active_targets, TABLE_TRADE_PLANNER, TABLE_TRADING_CAMPAIGNS
from src.logger_setup import setup_logging


def _prefixed(prefix: str, table: str) -> str:
    return f"{prefix}{table}" if prefix else table


def _add_column_if_missing(conn, table: str, campaigns_table: str) -> None:
    result = conn.execute(text(f"SHOW COLUMNS FROM `{table}` LIKE 'campaign_id'"))
    if result.first():
        print("  [OK]  Spalte 'campaign_id' bereits vorhanden")
        return

    conn.execute(text(
        f"ALTER TABLE `{table}` ADD COLUMN `campaign_id` INT DEFAULT NULL "
        f"COMMENT 'Verknuepfung zur echten Kampagne (trading_campaigns)' AFTER `environment`"
    ))
    print("  [NEU] Spalte 'campaign_id' hinzugefuegt")

    conn.execute(text(f"ALTER TABLE `{table}` ADD INDEX `idx_campaign_id` (`campaign_id`)"))
    print("  [NEU] Index 'idx_campaign_id' hinzugefuegt")

    conn.execute(text(
        f"ALTER TABLE `{table}` ADD CONSTRAINT `fk_{table}_campaign_id` "
        f"FOREIGN KEY (`campaign_id`) REFERENCES `{campaigns_table}`(`id`) ON DELETE SET NULL"
    ))
    print(f"  [NEU] Foreign Key auf '{campaigns_table}' hinzugefuegt")


def migrate_target(environment: str, prefix: str, logger) -> None:
    logger.info(f"[{environment.upper()} / prefix='{prefix}'] Starte Migration ...")
    table = _prefixed(prefix, TABLE_TRADE_PLANNER)
    campaigns_table = _prefixed(prefix, TABLE_TRADING_CAMPAIGNS)

    engine = get_engine(environment)
    with engine.begin() as conn:
        print(f"\n  Tabelle: {table}")
        _add_column_if_missing(conn, table, campaigns_table)
        logger.info(f"[{environment.upper()}] Migration abgeschlossen")


def main():
    logger, _ = setup_logging("migrate_add_campaign_id_to_trade_planner")

    if len(sys.argv) == 3:
        targets = [{"environment": sys.argv[1], "prefix": sys.argv[2]}]
    else:
        targets = load_active_targets()
        if not targets:
            logger.error("Keine aktiven Targets in pipeline.toml gefunden.")
            sys.exit(1)

    print(f"\n=== campaign_id-Migration ({len(targets)} Target(s)) ===\n")
    for t in targets:
        try:
            migrate_target(t["environment"], t["prefix"], logger)
        except Exception as e:
            logger.error(f"Fehler bei {t['environment']}/{t['prefix']}: {e}")
            raise

    print("\n=== Migration abgeschlossen ===\n")


if __name__ == "__main__":
    main()
