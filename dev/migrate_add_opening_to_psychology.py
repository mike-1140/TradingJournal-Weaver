"""
Migration: Psychologie-Eintraege einer Eroeffnung zuordnen
============================================================
Fuegt `campaign_id` und `opened_at` zu `psychology_entries` hinzu und ordnet bestehende Eintraege
ueber Strategie-ID bzw. Trade-ID der Eroeffnung im Ledger zu. Die Lektion wandert dabei in das
gemeinsame Feld `trade_planner.lessons_learned`; fehlt dort der Eintrag zur Eroeffnung, wird er
angelegt. Nicht zuzuordnende Eintraege bleiben unveraendert. Idempotent: bereits zugeordnete
Eintraege werden uebersprungen.

Aufruf:
  python -m dev.migrate_add_opening_to_psychology                        # alle aktiven Targets
  python -m dev.migrate_add_opening_to_psychology money dein_user_       # einzelnes Target
  python -m dev.migrate_add_opening_to_psychology money dein_user_ --probelauf
"""

import sys
from sqlalchemy import text
from src.config import (get_engine, load_active_targets, TABLE_CAMPAIGN_LEDGER, TABLE_PSYCHOLOGY_ENTRIES,
                        TABLE_TRADE_PLANNER, TABLE_TRADES_CLOSE, TABLE_TRADES_OPEN, TABLE_TRADING_CAMPAIGNS)
from src.logger_setup import setup_logging

OPENING_ACTIONS = ("OPT_PUT_SELL", "OPT_CALL_SELL", "OPT_PUT_BUY", "OPT_CALL_BUY", "STK_BUY", "STK_SELL")
ACTIONS_SQL = ", ".join(f"'{a}'" for a in OPENING_ACTIONS)


def _prefixed(prefix: str, table: str) -> str:
    return f"{prefix}{table}" if prefix else table


def _add_columns_if_missing(conn, table: str, dry_run: bool) -> bool:
    """True, wenn die Spalten (nun) vorhanden sind."""
    if conn.execute(text(f"SHOW COLUMNS FROM `{table}` LIKE 'opened_at'")).first():
        print("  [OK]  Spalten 'campaign_id'/'opened_at' bereits vorhanden")
        return True
    if dry_run:
        print("  [PROBELAUF] Spalten 'campaign_id'/'opened_at' wuerden hinzugefuegt")
        return False
    conn.execute(text(
        f"ALTER TABLE `{table}` "
        f"ADD COLUMN `campaign_id` INT DEFAULT NULL COMMENT 'Kampagne der Eroeffnung' AFTER `trade_type`, "
        f"ADD COLUMN `opened_at` DATETIME DEFAULT NULL COMMENT 'Eroeffnung innerhalb der Kampagne' AFTER `campaign_id`, "
        f"ADD INDEX `idx_campaign_opening` (`campaign_id`, `opened_at`)"
    ))
    print("  [NEU] Spalten 'campaign_id'/'opened_at' hinzugefuegt")
    return True


def _opening_of(conn, entry, t_ledger: str, t_open: str, t_close: str):
    """(campaign_id, dateTime) der Eroeffnung, oder None. Ueber die offene Tranche, sonst den geschlossenen Trade."""
    open_ids = []
    if entry["opt_strategyID"]:
        open_ids = conn.execute(text(f"SELECT id FROM `{t_open}` WHERE opt_strategyID = :s"),
                                {"s": entry["opt_strategyID"]}).scalars().all()
    elif entry["trade_id"] and entry["trade_type"] == "open":
        open_ids = [entry["trade_id"]]
    if open_ids:
        ids = ", ".join(str(int(i)) for i in open_ids)
        row = conn.execute(text(
            f"SELECT campaign_id, dateTime FROM `{t_ledger}` WHERE source_table = 'TRADES_OPEN' "
            f"AND source_id IN ({ids}) AND action IN ({ACTIONS_SQL}) ORDER BY dateTime, id LIMIT 1"
        )).first()
        if row:
            return row

    closed = None
    if entry["opt_strategyID"]:
        closed = conn.execute(text(f"SELECT symbol, dateTimeOpen FROM `{t_close}` WHERE opt_strategyID = :s ORDER BY dateTimeOpen LIMIT 1"),
                              {"s": entry["opt_strategyID"]}).first()
    elif entry["trade_id"] and entry["trade_type"] == "closed":
        closed = conn.execute(text(f"SELECT symbol, dateTimeOpen FROM `{t_close}` WHERE id = :i"),
                              {"i": entry["trade_id"]}).first()
    if closed:
        return conn.execute(text(
            f"SELECT campaign_id, dateTime FROM `{t_ledger}` WHERE symbol = :s AND dateTime = :d "
            f"AND action IN ({ACTIONS_SQL}) ORDER BY id LIMIT 1"
        ), {"s": closed[0], "d": closed[1]}).first()
    return None


def _move_lesson(conn, entry, campaign_id, opened_at, t_plan: str, t_campaigns: str, dry_run: bool) -> str:
    plan = conn.execute(text(f"SELECT id, lessons_learned FROM `{t_plan}` WHERE campaign_id = :c AND opened_at = :o"),
                        {"c": campaign_id, "o": opened_at}).first()
    if plan and plan[1]:
        return f"Lektion bleibt nur im alten Feld, Log #{plan[0]} hat schon einen Abschluss"
    if plan:
        if not dry_run:
            conn.execute(text(f"UPDATE `{t_plan}` SET lessons_learned = :l WHERE id = :i"), {"l": entry["lesson"], "i": plan[0]})
        return f"Lektion in Log #{plan[0]}"
    if not dry_run:
        symbol = conn.execute(text(f"SELECT symbol FROM `{t_campaigns}` WHERE id = :c"), {"c": campaign_id}).scalar()
        conn.execute(text(
            f"INSERT INTO `{t_plan}` (environment, campaign_id, opened_at, underlying, date_open, status, lessons_learned) "
            f"VALUES (:e, :c, :o, :u, :d, 'open', :l)"
        ), {"e": entry["environment"], "c": campaign_id, "o": opened_at, "u": symbol or entry["symbol"],
            "d": opened_at.date(), "l": entry["lesson"]})
    return "Lektion in NEUEN Log-Eintrag"


def migrate_target(environment: str, prefix: str, logger, dry_run: bool = False) -> None:
    logger.info(f"[{environment.upper()} / prefix='{prefix}'] Starte Migration ...")
    t_entries = _prefixed(prefix, TABLE_PSYCHOLOGY_ENTRIES)
    t_ledger = _prefixed(prefix, TABLE_CAMPAIGN_LEDGER)
    t_open = _prefixed(prefix, TABLE_TRADES_OPEN)
    t_close = _prefixed(prefix, TABLE_TRADES_CLOSE)
    t_plan = _prefixed(prefix, TABLE_TRADE_PLANNER)
    t_campaigns = _prefixed(prefix, TABLE_TRADING_CAMPAIGNS)

    with get_engine(environment).begin() as conn:
        print(f"\n  Tabelle: {t_entries}")
        if not conn.execute(text(f"SHOW TABLES LIKE '{t_entries}'")).first():
            print("  [SKIP] Psychology-Modul hier nicht eingerichtet")
            return
        has_columns = _add_columns_if_missing(conn, t_entries, dry_run)
        missing = "WHERE campaign_id IS NULL" if has_columns else ""
        entries = conn.execute(text(f"SELECT * FROM `{t_entries}` {missing} ORDER BY trade_date, id")).mappings().all()
        done = 0
        for entry in entries:
            found = _opening_of(conn, entry, t_ledger, t_open, t_close)
            label = f"Eintrag #{entry['id']} {entry['symbol']} {entry['trade_date']}"
            if not found:
                print(f"  [--]  {label}: keine Eroeffnung gefunden, bleibt unzugeordnet")
                continue
            campaign_id, opened_at = found[0], found[1]
            note = _move_lesson(conn, entry, campaign_id, opened_at, t_plan, t_campaigns, dry_run) if entry["lesson"] else "keine Lektion"
            print(f"  {'[PROBELAUF]' if dry_run else '[NEU]'} {label} -> Kampagne {campaign_id}, {opened_at}; {note}")
            if not dry_run:
                conn.execute(text(f"UPDATE `{t_entries}` SET campaign_id = :c, opened_at = :o WHERE id = :i"),
                             {"c": campaign_id, "o": opened_at, "i": entry["id"]})
            done += 1
        print(f"  {done} von {len(entries)} Eintrag/Eintraegen zugeordnet")
        logger.info(f"[{environment.upper()}] Migration abgeschlossen")


def main():
    logger, _ = setup_logging("migrate_add_opening_to_psychology")
    dry_run = "--probelauf" in sys.argv[1:]
    args = [a for a in sys.argv[1:] if a != "--probelauf"]

    if len(args) == 2:
        targets = [{"environment": args[0], "prefix": args[1]}]
    else:
        targets = load_active_targets()
        if not targets:
            logger.error("Keine aktiven Targets in pipeline.toml gefunden.")
            sys.exit(1)

    print(f"\n=== Psychologie-Eroeffnung-Migration ({len(targets)} Target(s)){' PROBELAUF' if dry_run else ''} ===\n")
    for t in targets:
        try:
            migrate_target(t["environment"], t["prefix"], logger, dry_run)
        except Exception as e:
            logger.error(f"Fehler bei {t['environment']}/{t['prefix']}: {e}")
            raise

    print("\n=== Migration abgeschlossen ===\n")


if __name__ == "__main__":
    main()
