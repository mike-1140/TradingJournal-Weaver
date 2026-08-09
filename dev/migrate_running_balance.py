"""
Migration: Running Balance im campaign_ledger nachfüllen
========================================================
Führt zwei Schritte aus:
  1. ALTER TABLE: Fügt cum_pnl, cum_commission, cum_premium hinzu (falls noch nicht vorhanden)
  2. UPDATE:      Berechnet die kumulierten Salden per Window-Function für alle bestehenden Zeilen

Aufruf:
  python src/migrate_running_balance.py               # alle aktiven Targets aus pipeline.toml
  python src/migrate_running_balance.py money mike_   # einzelnes Target
"""

import sys
from sqlalchemy import text
from src.config import get_engine, load_active_targets, TABLE_CAMPAIGN_LEDGER
from src.logger_setup import setup_logging


def _prefixed(prefix: str, table: str) -> str:
    return f"{prefix}{table}" if prefix else table


def _add_columns_if_missing(conn, table: str) -> None:
    """Fügt die drei Running-Balance-Spalten hinzu, falls sie noch nicht existieren."""
    new_cols = [
        ("cum_pnl",        "DECIMAL(19,4) DEFAULT NULL COMMENT 'kumulierter realisierter P&L dieser Kampagne'"),
        ("cum_commission",  "DECIMAL(19,4) DEFAULT NULL COMMENT 'kumulierte Kommissionen dieser Kampagne'"),
        ("cum_premium",     "DECIMAL(19,4) DEFAULT NULL COMMENT 'kumulierte Erlöse (Prämien + Aktienerlöse) dieser Kampagne'"),
    ]

    # Vorhandene Spalten abfragen
    result = conn.execute(text(f"SHOW COLUMNS FROM `{table}`"))
    existing = {row[0] for row in result}

    for col_name, col_def in new_cols:
        if col_name not in existing:
            conn.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `{col_name}` {col_def}"))
            print(f"  [NEU] Spalte '{col_name}' hinzugefuegt")
        else:
            print(f"  [OK]  Spalte '{col_name}' bereits vorhanden")


def _update_running_balances(conn, table: str) -> int:
    """
    Berechnet kumulierte Salden per Window-Function und schreibt sie in die Tabelle.
    Verarbeitet nur Zeilen wo cum_pnl IS NULL (d.h. noch nicht migriert).
    """
    # Prüfe ob es Zeilen zu migrieren gibt
    count_result = conn.execute(text(f"SELECT COUNT(*) FROM `{table}` WHERE cum_pnl IS NULL"))
    count = count_result.scalar()
    if count == 0:
        print("  [OK]  Keine Zeilen zu migrieren (alle bereits befuellt)")
        return 0

    sql = text(f"""
        UPDATE `{table}` cl
        JOIN (
            SELECT
                id,
                SUM(realized_pnl) OVER (
                    PARTITION BY campaign_id
                    ORDER BY dateTime, id
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS new_cum_pnl,
                SUM(commission) OVER (
                    PARTITION BY campaign_id
                    ORDER BY dateTime, id
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS new_cum_commission,
                SUM(proceeds) OVER (
                    PARTITION BY campaign_id
                    ORDER BY dateTime, id
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS new_cum_premium
            FROM `{table}`
        ) calc ON cl.id = calc.id
        SET
            cl.cum_pnl        = calc.new_cum_pnl,
            cl.cum_commission = calc.new_cum_commission,
            cl.cum_premium    = calc.new_cum_premium
        WHERE cl.cum_pnl IS NULL
    """)
    result = conn.execute(sql)
    return result.rowcount


def migrate_target(environment: str, prefix: str, logger) -> None:
    logger.info(f"[{environment.upper()} / prefix='{prefix}'] Starte Migration ...")
    table = _prefixed(prefix, TABLE_CAMPAIGN_LEDGER)

    engine = get_engine(environment)
    with engine.begin() as conn:
        print(f"\n  Tabelle: {table}")
        _add_columns_if_missing(conn, table)
        rows = _update_running_balances(conn, table)
        if rows:
            print(f"  [OK]  {rows} Zeilen aktualisiert")
        logger.info(f"[{environment.upper()}] Migration abgeschlossen ({rows} Zeilen)")


def main():
    logger, _ = setup_logging("migrate_running_balance")

    # Einzelnes Target per CLI-Argument: python migrate_running_balance.py money mike_
    if len(sys.argv) == 3:
        targets = [{"environment": sys.argv[1], "prefix": sys.argv[2]}]
    else:
        targets = load_active_targets()
        if not targets:
            logger.error("Keine aktiven Targets in pipeline.toml gefunden.")
            sys.exit(1)

    print(f"\n=== Running-Balance-Migration ({len(targets)} Target(s)) ===\n")
    for t in targets:
        try:
            migrate_target(t["environment"], t["prefix"], logger)
        except Exception as e:
            logger.error(f"Fehler bei {t['environment']}/{t['prefix']}: {e}")
            raise

    print("\n=== Migration abgeschlossen ===\n")


if __name__ == "__main__":
    main()
