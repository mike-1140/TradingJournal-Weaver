# Trading Journal 3.0 — Befehlsreferenz

## Environments

| Kürzel | Datenbank | Beschreibung |
|---|---|---|
| `money` | `ibkr_money` | Live-Trading |
| `paper` | `ibkr_paper` | Paper-Trading |
| `test` | `ibkr_test` | Test/Entwicklung |
| `autom_money` | `ibkr_autom_money` | Automatisiertes Live-Trading |
| `autom_paper` | `ibkr_autom_paper` | Automatisiertes Paper-Trading |

## Table-Prefix

Jeder User hat einen eigenen Tabellen-Prefix. Standard aus `.env` (`TABLE_PREFIX`).

| User | Prefix |
|---|---|
| mike | `mike_` |
| karola | `karola_` |

Beispiel: Prefix `mike_` → Tabellen `mike_trades_raw`, `mike_trades_open`, ...

---

## run_pipeline.py — Vollständiger Pipeline-Runner

Konfiguration in `pipeline.toml`. Führt alle 4 Schritte automatisch aus.

```bash
# Alles ausführen (laut pipeline.toml)
python run_pipeline.py

# Nur bestimmte User
python run_pipeline.py --users mike
python run_pipeline.py --users mike karola

# Nur bestimmte Environments
python run_pipeline.py --envs money
python run_pipeline.py --envs money paper

# Nur bestimmte Steps
python run_pipeline.py --steps fetch_emails
python run_pipeline.py --steps import process
python run_pipeline.py --steps fetch_emails import process summary

# Kombinationen
python run_pipeline.py --users mike --envs money
python run_pipeline.py --users mike --envs money --steps import process

# Vorschau ohne Ausführung (zeigt alle Steps und Befehle)
python run_pipeline.py --dry-run
python run_pipeline.py --users mike --dry-run

# Andere Konfigurationsdatei verwenden
python run_pipeline.py --config meine_pipeline.toml
```

**Verfügbare Steps:**

| Step | Script | Läuft pro |
|---|---|---|
| `fetch_emails` | `src/get_flexquery_emails.py` | Einmal gesamt |
| `import` | `src/import_ibkr_trades.py` | User × Environment |
| `process` | `src/process_ibkr_trades.py` | User × Environment |
| `summary` | `src/xml_append_summary.py` | Environment (einmal je Env) |

---

## get_flexquery_emails.py — E-Mails abrufen

Lädt IBKR FlexQuery XML-Anhänge aus dem Mail-Postfach und speichert sie
in die entsprechenden Environment-Ordner (`C:\Trade_XML\{env}\`).

```bash
python src/get_flexquery_emails.py
```

Keine Argumente. Zugangsdaten aus `.env` (`IMAP_USERNAME`, `IMAP_PASSWORD`, `IMAP_SERVER`).

---

## import_ibkr_trades.py — XML → trades_raw

Liest XML-Dateien aus dem Environment-Ordner und schreibt sie in `trades_raw`.

```bash
# Pflichtargument: Environment
python src/import_ibkr_trades.py money
python src/import_ibkr_trades.py paper
python src/import_ibkr_trades.py test
python src/import_ibkr_trades.py autom_money
python src/import_ibkr_trades.py autom_paper

# Mit Table-Prefix (überschreibt TABLE_PREFIX aus .env)
python src/import_ibkr_trades.py money mike_
python src/import_ibkr_trades.py money karola_

# Aus summary.xml importieren statt einzelner XML-Dateien
python src/import_ibkr_trades.py money from_summary
python src/import_ibkr_trades.py money mike_ from_summary
```

**Argumente:**
| Position | Wert | Pflicht |
|---|---|---|
| 1 | Environment (`money` \| `paper` \| `test` \| `autom_money` \| `autom_paper`) | Ja |
| 2 | Table-Prefix (z.B. `mike_`) | Nein (Standard aus `.env`) |
| - | `from_summary` (beliebige Position) | Nein |

---

## process_ibkr_trades.py — trades_raw → trades_open / trades_close

Verarbeitet unverarbeitete Einträge aus `trades_raw` per FIFO-Matching.
Schreibt Ergebnisse in `trades_open`, `trades_close`, `trading_campaigns`, `campaign_ledger`.

```bash
# Pflichtargument: Environment
python src/process_ibkr_trades.py money
python src/process_ibkr_trades.py paper
python src/process_ibkr_trades.py test
python src/process_ibkr_trades.py autom_money
python src/process_ibkr_trades.py autom_paper

# Mit Table-Prefix (überschreibt TABLE_PREFIX aus .env)
python src/process_ibkr_trades.py money mike_
python src/process_ibkr_trades.py money karola_
```

**Argumente:**
| Position | Wert | Pflicht |
|---|---|---|
| 1 | Environment | Ja |
| 2 | Table-Prefix | Nein (Standard aus `.env`) |

---

## xml_append_summary.py — Einzel-XMLs zu summary.xml zusammenfassen

Liest neue `flex.*.xml`-Dateien aus `{env}/processed/` und aktualisiert `summary.xml`.
Keine Duplikate (fromDate eindeutig), aufsteigende Reihenfolge, Performance-Cache.

```bash
# Standard: paper
python src/xml_append_summary.py

# Mit Environment-Angabe
python src/xml_append_summary.py money
python src/xml_append_summary.py paper
python src/xml_append_summary.py test
python src/xml_append_summary.py autom_money
python src/xml_append_summary.py autom_paper
```

**Argumente:**
| Position | Wert | Pflicht |
|---|---|---|
| 1 | Environment | Nein (Standard: `paper`) |

---

## reset_IBKR_DB.py — Datenbank initialisieren

Legt die Datenbank und alle Tabellen neu an (aus `sql/`-Schemas).
**Achtung: Löscht alle bestehenden Daten!** Nur beim ersten Setup oder nach Reset verwenden.

```bash
# Pflichtargument: Environment
python src/reset_IBKR_DB.py money
python src/reset_IBKR_DB.py paper
python src/reset_IBKR_DB.py test
python src/reset_IBKR_DB.py autom_money
python src/reset_IBKR_DB.py autom_paper

# Mit Table-Prefix
python src/reset_IBKR_DB.py money mike_
python src/reset_IBKR_DB.py money karola_
```

**Argumente:**
| Position | Wert | Pflicht |
|---|---|---|
| 1 | Environment | Ja |
| 2 | Table-Prefix | Nein (Standard aus `.env`) |

---

## Typischer Ablauf

### Erster Setup (einmalig)
```bash
python src/reset_IBKR_DB.py money mike_
python src/reset_IBKR_DB.py paper mike_
```

### Täglicher Lauf (manuell, Schritt für Schritt)
```bash
python src/get_flexquery_emails.py
python src/import_ibkr_trades.py money mike_
python src/process_ibkr_trades.py money mike_
python src/xml_summary_creator.py money
```

### Täglicher Lauf (automatisch, alle User/Envs)
```bash
python run_pipeline.py
```

### Nur einen User neu verarbeiten
```bash
python run_pipeline.py --users mike --steps process
```

### Nur Emails holen und importieren
```bash
python run_pipeline.py --steps fetch_emails import
```
