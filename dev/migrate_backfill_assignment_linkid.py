"""
Migration: linkID bei Assignment/Exercise nachtraeglich auffuellen
====================================================================
Backfill fuer den linkID-Bug in OpenTradeSchema.to_closed_trade() /
partial_close_new_open() (siehe trade_schemas/open_trade.py, gefixt am
2026-07-31): linkID wurde bislang faelschlich vom Open-Trade statt vom
Close-Event uebernommen. Optionen tragen beim Eroeffnen nie eine linkID,
dadurch blieb sie bei Assignment/Exercise-Closes leer, obwohl book_trades.py
sie beim Verarbeiten korrekt auf den schliessenden Raw-Trade UND den
zugehoerigen Stock-Trade gesetzt hatte.

Dieses Skript holt die verlorene linkID nachtraeglich aus trades_raw
(Match ueber tradeIDClose = trades_raw.tradeID) fuer alle trades_close-Zeilen
mit closedBy IN ('ASSIGNMENT','EXERCISE') und leerer linkID. Rein additiv
(UPDATE nur wo linkID aktuell NULL/leer ist) — mehrfach ausfuehrbar.

Aufruf:
  python src/migrate_backfill_assignment_linkid.py               # alle aktiven Targets aus pipeline.toml
  python src/migrate_backfill_assignment_linkid.py money mike_    # einzelnes Target
"""

import sys
from sqlalchemy import text
from src.config import get_engine, load_active_targets, TABLE_TRADES_CLOSE, TABLE_TRADES_RAW
from src.logger_setup import setup_logging


def _prefixed(prefix: str, table: str) -> str:
    return f"{prefix}{table}" if prefix else table


def _backfill_linkid(conn, close_table: str, raw_table: str) -> None:
    pending = conn.execute(text(
        f"SELECT COUNT(*) FROM `{close_table}` "
        f"WHERE closedBy IN ('ASSIGNMENT','EXERCISE') AND (linkID IS NULL OR linkID = '')"
    )).scalar()

    if pending == 0:
        print("  [OK]  keine offenen Assignment/Exercise-Closes ohne linkID")
        return

    matchable = conn.execute(text(
        f"SELECT COUNT(*) FROM `{close_table}` tc "
        f"JOIN `{raw_table}` tr ON tr.tradeID = tc.tradeIDClose "
        f"WHERE tc.closedBy IN ('ASSIGNMENT','EXERCISE') "
        f"AND (tc.linkID IS NULL OR tc.linkID = '') "
        f"AND tr.linkID IS NOT NULL AND tr.linkID != ''"
    )).scalar()

    print(f"  {pending} Zeile(n) ohne linkID gefunden, {matchable} davon ueber trades_raw auffuellbar")

    if matchable == 0:
        return

    result = conn.execute(text(
        f"UPDATE `{close_table}` tc "
        f"JOIN `{raw_table}` tr ON tr.tradeID = tc.tradeIDClose "
        f"SET tc.linkID = tr.linkID "
        f"WHERE tc.closedBy IN ('ASSIGNMENT','EXERCISE') "
        f"AND (tc.linkID IS NULL OR tc.linkID = '') "
        f"AND tr.linkID IS NOT NULL AND tr.linkID != ''"
    ))
    print(f"  [NEU] {result.rowcount} Zeile(n) linkID nachtraeglich gesetzt")

    still_open = pending - matchable
    if still_open > 0:
        print(f"  [INFO] {still_open} Zeile(n) bleiben ohne linkID (kein Stock-Gegenstueck, z.B. Cash Settlement)")


def migrate_target(environment: str, prefix: str, logger) -> None:
    logger.info(f"[{environment.upper()} / prefix='{prefix}'] Starte Backfill ...")
    close_table = _prefixed(prefix, TABLE_TRADES_CLOSE)
    raw_table = _prefixed(prefix, TABLE_TRADES_RAW)

    engine = get_engine(environment)
    with engine.begin() as conn:
        print(f"\n  Tabelle: {close_table}")
        _backfill_linkid(conn, close_table, raw_table)
        logger.info(f"[{environment.upper()}] Backfill abgeschlossen")


def main():
    logger, _ = setup_logging("migrate_backfill_assignment_linkid")

    if len(sys.argv) == 3:
        targets = [{"environment": sys.argv[1], "prefix": sys.argv[2]}]
    else:
        targets = load_active_targets()
        if not targets:
            logger.error("Keine aktiven Targets in pipeline.toml gefunden.")
            sys.exit(1)

    print(f"\n=== linkID-Backfill Assignment/Exercise ({len(targets)} Target(s)) ===\n")
    for t in targets:
        try:
            migrate_target(t["environment"], t["prefix"], logger)
        except Exception as e:
            logger.error(f"Fehler bei {t['environment']}/{t['prefix']}: {e}")
            raise

    print("\n=== Backfill abgeschlossen ===\n")


if __name__ == "__main__":
    main()
