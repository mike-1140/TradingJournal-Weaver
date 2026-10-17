# Tests

## Ausführen

```bash
.venv\Scripts\activate
pytest tests/ -v
```

Einzelne Datei: `pytest tests/test_process_raw_trade.py -v`
Einzelner Test: `pytest tests/test_process_raw_trade.py::TestCase2aTeilschluss -v`

## CI (GitHub Actions)

`.github/workflows/tests.yml` — läuft auf jedem Push/PR gegen `master` und auf jedem PR: frisches Ubuntu, nur `requirements.txt` installiert, kein `.env`/keine DB nötig (siehe „Keine Datenbank nötig" oben). Lokal als Trockenlauf geprüft: `pip install -r requirements.txt` in einem leeren venv, alle Tests grün.

Keine Datenbank nötig — alle Tests laufen komplett gegen In-Memory-Fakes, siehe unten.

## Testdateien

| Datei | Prüft |
|---|---|
| `test_safe_filename.py` | `_safe_filename()` — Path-Traversal-Schutz beim Mail-Import (`get_flexquery_emails.py`) |
| `test_open_trade_schema.py` | `OpenTradeSchema.to_closed_trade()` / `partial_close_new_open()` / `validate()` — reine Dict-Rechnung, keine Mocks nötig |
| `test_process_raw_trade.py` | `process_raw_trade()` — die komplette FIFO-Fallunterscheidung + Bug 2/Bug 4, über die Fakes in `conftest.py` |
| `test_split_handling.py` | `_resolve_split_holdings_symbol()` — welches Symbol nach einem Stock Split im Tracker nachgeschlagen wird |
| `test_campaign_cleanup.py` | `InventoryTracker.close_old_pending_campaigns()` — Gap-Fenster wird ab `reference_date` berechnet, nicht ab heute |
| `test_flexquery_email_import.py` | `_process_flexquery_mails()` / `_process_activity_statement_mails()` — Mails werden immer geloescht, unabhaengig davon ob/was gespeichert wurde |
| `test_run_pipeline_steps.py` | `run_pipeline.py` — jeder Step in `VALID_STEPS`/`STEP_SCRIPTS` zeigt auf ein existierendes Modul; entfernter Step `snapshot_import` ist nicht mehr wählbar |

## Fixtures in `conftest.py`

| Fixture | Ersetzt | Wofür |
|---|---|---|
| `dummy_logger` | `Logger` | Sammelt Log-Aufrufe im Speicher (`.records`), statt in eine Datei zu schreiben |
| `dummy_db` | `DBAccess` | Zeichnet `insert_dataframe`/`select`-Aufrufe auf, ohne echte DB-Verbindung |
| `fake_repo` | `TradeRepository` | Hält offene Tranchen als Liste von Dicts im Speicher; bildet `get_open_trades()`, `insert_open_trade()`, `insert_closed_trade()`, `mark_trade_processed()` nach |
| `fake_tracker` | `InventoryTracker` | `.holdings`-Dict direkt befüllbar; `link_to_campaign_new()` zeichnet nur die Aufrufparameter auf, statt echtes SQL gegen `campaign_ledger` abzusetzen |

`fake_repo`/`fake_tracker` bilden nur die Methoden nach, die `process_raw_trade()` tatsächlich aufruft — keine vollständigen Nachbauten der echten Klassen. `FakeInventoryDbConn` (nur in `test_campaign_cleanup.py`) und `FakeImap` (nur in `test_flexquery_email_import.py`) sind aus demselben Grund lokal statt in `conftest.py`, da sie bisher nur von jeweils einer Testdatei gebraucht werden.

## Was inhaltlich abgedeckt ist

**FIFO-Fallunterscheidung** (`process_raw_trade()`, Case-Tabelle siehe `CLAUDE.md`):
- Case 1 — Position eröffnen (keine offene Tranche vorhanden)
- Case 2c — exakter Close (Mengen heben sich auf)
- Case 2a — Teilschluss (offene Tranche größer, Rest wird als `SPLIT_REST` neu eingebucht)
- Case 2b + Reversal — Close größer als die Tranche (Tranche komplett verbraucht, Überhang wird als `REV_OPEN`-Gegenposition eröffnet)

**Regressionstests für alle dokumentierten, bereits gefixten Bugs** (siehe „Known Bugs" in `CLAUDE.md` + Memory):
- **Bug 1** — P&L wurde bei Teil-Closes nicht mit dem Schließungsanteil skaliert
- **Bug 2** — OPT-Close bucht 0 im Ledger statt der echten netcash/proceeds/commission-Werte (nur der reguläre Buy-/Sell-to-close-Zweig, nicht Expiration/Assignment/Cash-Settlement — dort ist ein Nullwert korrekt, da kein Cash fließt)
- **Bug 3** — ROI nutzte einen falschen Nenner statt der tatsächlichen Einstiegskosten
- **Bug 4** — Ledger-Buchung beim Schließen enthielt fälschlich einen Anteil der Open-Commission, obwohl die schon bei `TRADE_OPEN` komplett gebucht wurde (3 Tests, je einer für Case 2a/2b/2c — mit bewusst überdimensionierter Open-Commission als Marker, damit ein Wiederauftreten sofort auffällt)
- **Enum-Bug** — `validate()` schlug bei `TradeStatus`-Enum-Werten fehl (Python-3.11+-Änderung im `str()`-Verhalten von str-Enums)
- **Split-Bug** — Kampagne blieb nach einem Stock Split `ACTIVE`, weil `underlyingSymbol` statt des neuen `symbol` im Tracker nachgeschlagen wurde (Bugfixture-Logik dafür in `_resolve_split_holdings_symbol()` extrahiert, da sie ursprünglich inline in `process_trades()` saß — nicht ohne echte DB aufrufbar)
- **Kampagnen-Gap-Bug** — `close_old_pending_campaigns()` rechnete mit `datetime.now()` statt dem Datum des ersten Trades → bei verzögertem AUTOM-Import wurden PENDING-Kampagnen zu früh geschlossen
- **get_flexquery_emails-Bug** — Mails blieben im Posteingang hängen: das `\Deleted`-Flag war an "Datei neu gespeichert" gekoppelt statt einmal pro Mail gesetzt zu werden

Diese Tests sind Stolperdrähte, keine Fehlersuche — der jeweilige Fehler ist bereits behoben. Der Test verhindert, dass er unbemerkt zurückkommt (eigener Refactor, externer PR, Nachbar-Änderung). Alle wurden verifiziert, indem der jeweilige Bug kurz testweise reintroduziert wurde (Test schlägt fehl → zurückgesetzt → wieder grün).

## Was noch NICHT abgedeckt ist

- Options-spezifische Pfade in `process_raw_trade()` (Assignment, Exercise, Cash Settlement, `OPTION_EXPIRATION`) — die bisherigen Case-Tests laufen überwiegend mit `assetCategory='STK'`
- `process_trades()` selbst (die Hauptschleife) — baut DB-Verbindung und Tracker fest intern auf, nicht ohne größeren Umbau injizierbar
- `apply_split()` / `_handle_split_trade()` — die Split-Erkennung/-Berechnung selbst (nur das Symbol-Nachschlagen danach ist getestet)
