# CLAUDE.md — Trading Journal 3.0

## Project Overview
Python system that imports IBKR (Interactive Brokers) FlexQuery XML reports and processes
them into a structured trading journal with P&L, campaign tracking, and open/closed positions.

**Assets handled:** STK (stocks), OPT (options), CASH (FX)
**Database:** MySQL (local, port 3306)
**Python:** 3.14
**Language:** Code comments and log messages are in German

---

## Entry Points

| Script | Purpose |
|---|---|
| `src/import_ibkr_trades.py` | Step 1: Parse XML → insert into `trades_raw` |
| `src/process_ibkr_trades.py` | Step 2: Process `trades_raw` → `trades_open` / `trades_close` |
| `tools/maintenance/reset_IBKR_DB.py` | First-time DB setup from `sql/` schema files (destruktiv!) |
| `tools/maintenance/cleanup_stale_positions.py` | Entfernt liegengebliebene offene Positionen (Open importiert, Close nie) rückstandsfrei aus `trades_open`/`campaign_ledger`/`trades_raw` inkl. Kampagnen-Korrektur; Dry-Run ist Standard, löschen nur mit `--ids/--symbols/--older-than/--all` + `--execute` |
| `run_pipeline.py` | Orchestriert alle Steps laut `pipeline.toml` |

**Import-Routing:** `import_ibkr_trades.py` scannt `C:\Trade_XML\incoming_mail\` (Mail) UND
`C:\Trade_XML\incoming_api\` (FlexQuery Web-API) gleichwertig, kein Dateinamen-Filter mehr.
User + Environment werden per accountId über `accounts.toml` ermittelt (maschinenspezifisch,
nicht versioniert, Vorlage `accounts.toml.example`; gelesen von `load_account_map()` /
`get_account_config()` in `src/config.py`, Key = letzte 4 Ziffern der accountId). Der
Tabellen-Prefix kommt aus `users.toml`. Unbekannte accountIds werden mit Warnung übersprungen. Checksum-Dedup verhindert doppelte Trades, falls
dieselben Daten über beide Kanäle ankommen.

### Running the pipeline
```bash
python -m src.import_ibkr_trades          # Auto-Modus: alle Accounts (Standard)
python -m src.import_ibkr_trades money mike_   # CLI-Override: nur dieses Environment/Prefix
python -m src.process_ibkr_trades money
# Environments: money | paper | test | autom_money | autom_paper
```

---

## Architecture
```
XML files (C:\Trade_XML\incoming_mail\ + incoming_api\, alle *.xml)
    → flex_parser.py          (orchestrates XML parsing)
    → day_trade_processor.py  (extracts Trade / OptionEAE / CorporateActions)
    → option_strategies.py    (detects multi-leg strategies)
    → book_trades.py          (matches IBKR BookTrades to EAE events)
    → trades_raw table        (raw import, processed=0)
    → process_ibkr_trades.py  (FIFO tranche matching)
    → trades_open / trades_close tables
    → InventoryTracker        (campaign lifecycle)
    → trading_campaigns + campaign_ledger tables
```

---

## Key Modules

| Module | Role |
|---|---|
| `src/parsers/flex_parser.py` | XML orchestrator, aggregates same-day trades |
| `src/parsers/day_trade_processor.py` | Extracts trades from XML elements |
| `src/parsers/option_strategies.py` | Detects Vertical/Calendar/Diagonal/Straddle/Strangle/Butterfly/Iron Condor — primär `ibOrderID`, Fallback 3s-Fenster |
| `src/parsers/inventory_tracker.py` | Campaign lifecycle: ACTIVE → PENDING → CLOSED (10-day gap) |
| `src/book_trades.py` | Matches BookTrades to OptionEAE events (Assignment/Expiry/CashSettlement) |
| `src/db/db_access.py` | `DBAccess` (low-level SQL) + `TradeRepository` (domain queries) |
| `src/trade_schemas/open_trade.py` | `OpenTradeSchema` — validation, `to_closed_trade()`, `partial_close_new_open()` |
| `src/trade_schemas/closed_trade.py` | `ClosedTradeSchema` — validation and logging |
| `src/utils/div_utils.py` | `to_decimal()`, `compute_checksum()`, `calculate_hold_metrics()` |
| `src/utils/corporate_utils.py` | Stock split detection |

---

## Database Tables

| Table | Purpose |
|---|---|
| `trades_raw` | All imports; `processed=0/1` flag controls processing |
| `trades_open` | FIFO tranches (one row per lot). **Achtung:** Geschlossene Tranchen werden nicht gelöscht, sondern nur auf `processed=1` gesetzt (History, siehe `db_access.delete_open_trade`) — wirklich offen ist nur `processed=0`, so filtert auch TradingJournal |
| `trades_close` | Completed trades with P&L, ROI, days held |
| `trading_campaigns` | Campaign per symbol (ACTIVE/PENDING/CLOSED) |
| `campaign_ledger` | Full audit journal: every action with cash flows |
| `symbols` | Instrument reference (conid, ISIN, underlying) |
| `trades_fx` | FX/cash trades (separate, not in campaign tracking) |

---

## process_ibkr_trades.py — FIFO Logic (process_raw_trade)

IBKR sign convention: **BUY → netCash negative, SELL → netCash positive**

| Case | Condition | Action |
|---|---|---|
| CASH | assetCategory == 'CASH' | Nur `processed=1` (kein FIFO, keine Kampagne); der `FX_EXCHANGE_FROM_/TO_`-Ledger-Zweig braucht `campaign_id` und läuft daher nie (CASH bekommt `campaign_id=None`). Die zwei `trades_raw`-Zeilen je Tausch haben `quantity` 1 = „von“ / 2 = „nach“ (Kennung, keine Menge); `trades_fx` (1 Zeile je Tausch) wird schon beim Import befüllt |
| Case 1 | Same direction or flat | INSERT `trades_open`, action=TRADE_OPEN |
| Case 2c | `open_abs == new_abs` | Full close → `trades_close` |
| Case 2a | `open_abs > new_abs` | Partial close → `trades_close` + re-insert remainder as SPLIT_REST |
| Case 2b | `new_abs > open_abs` | Consume full tranche, carry remainder to next iteration |
| Reversal | `remaining_qty != 0` after loop | INSERT `trades_open` with status=REV_OPEN |
| Split | `is_split == True` | Check vor `process_row_and_get_campaign()` — keine PENDING/ACTIVE-Zyklen; campaign_id aus `tracker.holdings`; `h['shares']` wird mit Faktor angepasst |

---

## Configuration

- `.env` — DB credentials, `DEFAULT_USER` (e.g. `mike`, Prefix wird aus `users.toml` aufgelöst) oder direkt `TABLE_PREFIX` als Override, environment DB names, API keys (z.B. Mail-Zugang für `get_flexquery_emails.py`)
- `users.toml` — zentrale User↔Prefix-Registry (einzige Quelle für z.B. `mike` → `mike_`); seit 2026-10-19 lokal/gitignored (Vorlage `users.toml.example`, echte Namen nicht im Repo). Fehlt ein in `accounts.toml`/`pipeline.toml` genannter User, wirft `config._registered_prefix()` einen `ValueError` statt leerem Prefix
- `pipeline.toml` — maschinenspezifisch, gitignored; aktive User/Environments dieser Maschine (siehe `pipeline.toml.example`)
- `accounts.toml` — maschinenspezifisch, gitignored; IBKR-Konto (letzte 4 Ziffern) → User + Environment (siehe `accounts.toml.example`)
- `src/config.py` — `get_engine(env)`, `DB_MAP`, `load_account_map()`/`get_account_config()` (liest `accounts.toml`), `load_users()`, table name constants
- `.gitignore` — `.env`, `pipeline.toml`, `accounts.toml`, `users.toml` ausgeschlossen (keine Secrets/Maschinenspezifika im Repo!)

Table names use an optional prefix (e.g. `mike_trades_raw`) for multi-user support.

---

## Git-Sicherheit

**Secrets gehören ausschließlich in `.env`, nie in den Code.**

Falls versehentlich ein Secret in der Git-History landet:
1. Secret sofort rotieren/widerrufen
2. `git filter-repo --path DATEI --invert-paths --force` (löscht Datei aus History + Working Tree + alle Remotes!)
3. Datei aus Backup/Local History wiederherstellen
4. `git remote add origin URL` (Remote wurde von filter-repo entfernt)
5. `git add`, `git commit`, `git push origin master --force`

---

## Known Bugs (found 2026-02-26, fixed 2026-02-27)

### ~~Bug 1 — CRITICAL: P&L multiplied in Case 2b multi-tranche closes~~ FIXED
**File:** `src/trade_schemas/open_trade.py`
`profit_close` now scaled by `close_portion` (same factor as `net_cash_close`).

### ~~Bug 2 — HIGH: OPT normal close records zero cash in campaign ledger~~ FIXED
**File:** `src/process_ibkr_trades.py`
OPT `else` branch now populates `netcash`, `proceeds`, `commission` from `cl_trade`.

### ~~Bug 3 — MEDIUM: ROI uses wrong denominator in `to_closed_trade`~~ FIXED
**File:** `src/trade_schemas/open_trade.py`
`calculate_roi` now uses `closed_trade['netCashOpen']` (buy cost) as denominator.

### ~~Bug 4 — LOW: Commission double-counted in ledger on full close~~ FIXED
**File:** `src/trade_schemas/open_trade.py`
`ibCommission` now stores close commission only; open commission removed from sum.
**Überholt (Stand 2026-10-17, gegen Code geprüft):** `ibCommission` = Open- + Close-Kommission —
in `to_closed_trade()` Open vollständig + Close anteilig (`close_portion`), in
`partial_close_new_open()` Open anteilig + Close vollständig. `profit` ist **brutto**
(`proceeds_open + proceeds_close`), Netto = `profit + ibCommission` (Kommission negativ).

---

## Development Notes

- Always use `Decimal` (not `float`) for financial values — `to_decimal()` helper available
- `clean_trade_dict()` in `process_ibkr_trades.py` normalizes Decimal fields before processing
- Checksums (MD5) prevent duplicate imports — based on tradeID+datetime+symbol+qty+price
- Tests live in `tests/` — uses `DummyLogger` and `DummyDBAccess` mocks from `conftest.py`
- The large commented-out block at the bottom of `process_ibkr_trades.py` is the old schema-delegation
  approach — it can be ignored/removed eventually

### Linter-Warnung: `open_trade.py`
Der Linter (PyCharm/Ruff) hat `closed_trade['status'] = status` in `to_closed_trade()` in den
`if pd.isna`-Block eingerückt → Status wurde nur bei leeren Werten gesetzt →
`ValidationError: Status must be 'Closed' or 'Expired'`.
Nach Linter-Läufen prüfen, dass die Zuweisung **außerhalb** des `if`-Blocks steht (Zeile ~200).
