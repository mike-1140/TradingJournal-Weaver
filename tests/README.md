# Tests

## Ausführen

```bash
.venv\Scripts\activate
pytest tests/ -v
```

Einzelne Datei: `pytest tests/test_process_raw_trade.py -v`
Einzelner Test: `pytest tests/test_process_raw_trade.py::TestCase2aTeilschluss -v`

Keine Datenbank nötig — alle Tests laufen komplett gegen In-Memory-Fakes, siehe unten.

## Testdateien

| Datei | Prüft |
|---|---|
| `test_safe_filename.py` | `_safe_filename()` — Path-Traversal-Schutz beim Mail-Import (`get_flexquery_emails.py`) |
| `test_open_trade_schema.py` | `OpenTradeSchema.to_closed_trade()` / `partial_close_new_open()` / `validate()` — reine Dict-Rechnung, keine Mocks nötig |
| `test_process_raw_trade.py` | `process_raw_trade()` — die komplette FIFO-Fallunterscheidung, über die Fakes in `conftest.py` |

## Fixtures in `conftest.py`

| Fixture | Ersetzt | Wofür |
|---|---|---|
| `dummy_logger` | `Logger` | Sammelt Log-Aufrufe im Speicher (`.records`), statt in eine Datei zu schreiben |
| `dummy_db` | `DBAccess` | Zeichnet `insert_dataframe`/`select`-Aufrufe auf, ohne echte DB-Verbindung |
| `fake_repo` | `TradeRepository` | Hält offene Tranchen als Liste von Dicts im Speicher; bildet `get_open_trades()`, `insert_open_trade()`, `insert_closed_trade()`, `mark_trade_processed()` nach |
| `fake_tracker` | `InventoryTracker` | `.holdings`-Dict direkt befüllbar; `link_to_campaign_new()` zeichnet nur die Aufrufparameter auf, statt echtes SQL gegen `campaign_ledger` abzusetzen |

`fake_repo`/`fake_tracker` bilden nur die Methoden nach, die `process_raw_trade()` tatsächlich aufruft — keine vollständigen Nachbauten der echten Klassen.

## Was inhaltlich abgedeckt ist

**FIFO-Fallunterscheidung** (`process_raw_trade()`, Case-Tabelle siehe `CLAUDE.md`):
- Case 1 — Position eröffnen (keine offene Tranche vorhanden)
- Case 2c — exakter Close (Mengen heben sich auf)
- Case 2a — Teilschluss (offene Tranche größer, Rest wird als `SPLIT_REST` neu eingebucht)
- Case 2b + Reversal — Close größer als die Tranche (Tranche komplett verbraucht, Überhang wird als `REV_OPEN`-Gegenposition eröffnet)

**Regressionstests für dokumentierte, bereits gefixte Bugs** (siehe „Known Bugs" in `CLAUDE.md`):
- **Bug 1** — P&L wurde bei Teil-Closes nicht mit dem Schließungsanteil skaliert
- **Bug 3** — ROI nutzte einen falschen Nenner statt der tatsächlichen Einstiegskosten
- **Bug 4** — Ledger-Buchung beim Schließen enthielt fälschlich einen Anteil der Open-Commission, obwohl die schon bei `TRADE_OPEN` komplett gebucht wurde (3 Tests, je einer für Case 2a/2b/2c — mit bewusst überdimensionierter Open-Commission als Marker, damit ein Wiederauftreten sofort auffällt)
- **Enum-Bug** — `validate()` schlug bei `TradeStatus`-Enum-Werten fehl (Python-3.11+-Änderung im `str()`-Verhalten von str-Enums)

Diese Tests sind Stolperdrähte, keine Fehlersuche — der jeweilige Fehler ist bereits behoben. Der Test verhindert, dass er unbemerkt zurückkommt (eigener Refactor, externer PR, Nachbar-Änderung).

## Was noch NICHT abgedeckt ist

- **Bug 2** (OPT-Close bucht 0 im Ledger) — noch kein Test
- **Split-Bug** (Kampagne bleibt `ACTIVE` nach Stock Split) — braucht Tracker mit vorbefülltem Holdings-Zustand
- **Kampagnen-Gap-Bug** (`close_old_pending_campaigns()`) — braucht Zeit-Mocking
- **get_flexquery_emails.py** (IMAP-Deletion-Bug) — braucht IMAP-Mock, kein DB-Bezug
- Options-spezifische Pfade in `process_raw_trade()` (Assignment, Exercise, Cash Settlement, `OPTION_EXPIRATION`) — die bisherigen Case-Tests laufen nur mit `assetCategory='STK'`
