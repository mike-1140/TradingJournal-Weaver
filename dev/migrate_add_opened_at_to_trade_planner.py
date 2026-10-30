"""
Migration: opened_at in trade_planner nachruesten
====================================================
Fuegt die Spalte `opened_at` hinzu: Zeitpunkt der Eroeffnung innerhalb der Kampagne, zu der ein
Log-Eintrag gehoert (Kommentar je Eroeffnung; die Zahlen kommen aus dem Ledger). Bestehende
verknuepfte Eintraege ohne Wert bekommen die erste Eroeffnung ihrer Kampagne. Idempotent.

Aufruf:
  python -m dev.migrate_add_opened_at_to_trade_planner                        # alle aktiven Targets
  python -m dev.migrate_add_opened_at_to_trade_planner money mike_            # einzelnes Target
  python -m dev.migrate_add_opened_at_to_trade_planner money mike_ --probelauf
"""

import sys
from sqlalchemy import text
from src.config import get_engine, load_active_targets, TABLE_TRADE_PLANNER, TABLE_CAMPAIGN_LEDGER
from src.logger_setup import setup_logging

OPENING_ACTIONS = ("OPT_PUT_SELL", "OPT_CALL_SELL", "OPT_PUT_BUY", "OPT_CALL_BUY", "STK_BUY", "STK_SELL")


def _prefixed(prefix: str, table: str) -> str:
    return f"{prefix}{table}" if prefix else table


def _add_column_if_missing(conn, table: str, dry_run: bool) -> bool:
    """True, wenn die Spalte (nun) vorhanden ist."""
    if conn.execute(text(f"SHOW COLUMNS FROM `{table}` LIKE 'opened_at'")).first():
        print("  [OK]  Spalte 'opened_at' bereits vorhanden")
        return True
    if dry_run:
        print("  [PROBELAUF] Spalte 'opened_at' wuerde hinzugefuegt")
        return False
    conn.execute(text(
        f"ALTER TABLE `{table}` ADD COLUMN `opened_at` DATETIME DEFAULT NULL "
        f"COMMENT 'Eroeffnung innerhalb der Kampagne, zu der dieser Eintrag gehoert' AFTER `campaign_id`"
    ))
    print("  [NEU] Spalte 'opened_at' hinzugefuegt")
    return True


def _backfill(conn, table: str, ledger: str, has_column: bool, dry_run: bool) -> int:
    missing = "AND p.opened_at IS NULL" if has_column else ""
    actions = ", ".join(f"'{a}'" for a in OPENING_ACTIONS)
    rows = conn.execute(text(
        f"SELECT p.id, p.underlying, "
        f"(SELECT MIN(l.dateTime) FROM `{ledger}` l WHERE l.campaign_id = p.campaign_id AND l.action IN ({actions})) AS first_open "
        f"FROM `{table}` p WHERE p.campaign_id IS NOT NULL {missing}"
    )).mappings().all()
    count = 0
    for row in rows:
        if row["first_open"] is None:
            print(f"  [--]  Eintrag #{row['id']} {row['underlying']}: Kampagne ohne Eroeffnung, bleibt leer")
            continue
        print(f"  {'[PROBELAUF]' if dry_run else '[NEU]'} Eintrag #{row['id']} {row['underlying']}: {row['first_open']}")
        if not dry_run:
            conn.execute(text(f"UPDATE `{table}` SET opened_at = :t WHERE id = :id"),
                         {"t": row["first_open"], "id": row["id"]})
        count += 1
    return count


def migrate_target(environment: str, prefix: str, logger, dry_run: bool = False) -> None:
    logger.info(f"[{environment.upper()} / prefix='{prefix}'] Starte Migration ...")
    table = _prefixed(prefix, TABLE_TRADE_PLANNER)
    ledger = _prefixed(prefix, TABLE_CAMPAIGN_LEDGER)

    engine = get_engine(environment)
    with engine.begin() as conn:
        print(f"\n  Tabelle: {table}")
        if not conn.execute(text(f"SHOW TABLES LIKE '{table}'")).first():
            print("  [--]  Tabelle nicht vorhanden, uebersprungen")
            return
        has_column = _add_column_if_missing(conn, table, dry_run)
        count = _backfill(conn, table, ledger, has_column, dry_run)
        print(f"  {count} Eintrag/Eintraege")
        logger.info(f"[{environment.upper()}] Migration abgeschlossen")


def main():
    logger, _ = setup_logging("migrate_add_opened_at_to_trade_planner")
    dry_run = "--probelauf" in sys.argv[1:]
    args = [a for a in sys.argv[1:] if a != "--probelauf"]

    if len(args) == 2:
        targets = [{"environment": args[0], "prefix": args[1]}]
    else:
        targets = load_active_targets()
        if not targets:
            logger.error("Keine aktiven Targets in pipeline.toml gefunden.")
            sys.exit(1)

    print(f"\n=== opened_at-Migration ({len(targets)} Target(s)){' PROBELAUF' if dry_run else ''} ===\n")
    for t in targets:
        try:
            migrate_target(t["environment"], t["prefix"], logger, dry_run)
        except Exception as e:
            logger.error(f"Fehler bei {t['environment']}/{t['prefix']}: {e}")
            raise

    print("\n=== Migration abgeschlossen ===\n")


if __name__ == "__main__":
    main()
