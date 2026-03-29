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

# Import aus summary.xml statt einzelner XML-Dateien
python run_pipeline.py --steps import --from-summary
python run_pipeline.py --steps import --from-summary --users mike
python run_pipeline.py --steps import --from-summary --envs autom_paper

# DB-Reset (destruktiv — Sicherheitsabfrage erscheint)
python run_pipeline.py --steps reset --users mike
python run_pipeline.py --steps reset --users mike --envs money
python run_pipeline.py --steps reset --force        # ohne Rückfrage

# Vorschau ohne Ausführung (zeigt alle Steps und Befehle)
python run_pipeline.py --dry-run
python run_pipeline.py --users mike --dry-run

# Andere Konfigurationsdatei verwenden
python run_pipeline.py --config meine_pipeline.toml
```

**Verfügbare Steps:**

| Step | Modul | Läuft pro |
|---|---|---|
| `fetch_emails` | `src.get_flexquery_emails` | Einmal gesamt |
| `import` | `src.import_ibkr_trades` | User × Environment |
| `process` | `src.process_ibkr_trades` | User × Environment |
| `summary` | `src.xml_append_summary` | Environment (einmal je Env) |
| `reset` | `src.reset_IBKR_DB` | User × Environment ⚠️ destruktiv |

---

## get_flexquery_emails.py — E-Mails abrufen

Lädt IBKR FlexQuery XML-Anhänge aus dem Mail-Postfach und speichert sie
in die entsprechenden Environment-Ordner (`C:\Trade_XML\{env}\`).

```bash
python -m src.get_flexquery_emails
```

Keine Argumente. Zugangsdaten aus `.env` (`IMAP_USERNAME`, `IMAP_PASSWORD`, `IMAP_SERVER`).

---

## import_ibkr_trades.py — XML → trades_raw

Liest XML-Dateien aus dem Environment-Ordner und schreibt sie in `trades_raw`.

```bash
# Pflichtargument: Environment
python -m src.import_ibkr_trades money
python -m src.import_ibkr_trades paper
python -m src.import_ibkr_trades test
python -m src.import_ibkr_trades autom_money
python -m src.import_ibkr_trades autom_paper

# Mit Table-Prefix (überschreibt TABLE_PREFIX aus .env)
python -m src.import_ibkr_trades money mike_
python -m src.import_ibkr_trades money karola_

# Aus summary.xml importieren statt einzelner XML-Dateien
python -m src.import_ibkr_trades money from_summary
python -m src.import_ibkr_trades money mike_ from_summary
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
python -m src.process_ibkr_trades money
python -m src.process_ibkr_trades paper
python -m src.process_ibkr_trades test
python -m src.process_ibkr_trades autom_money
python -m src.process_ibkr_trades autom_paper

# Mit Table-Prefix (überschreibt TABLE_PREFIX aus .env)
python -m src.process_ibkr_trades money mike_
python -m src.process_ibkr_trades money karola_
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
python -m src.xml_append_summary

# Mit Environment-Angabe
python -m src.xml_append_summary money
python -m src.xml_append_summary paper
python -m src.xml_append_summary test
python -m src.xml_append_summary autom_money
python -m src.xml_append_summary autom_paper
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
python -m src.reset_IBKR_DB money
python -m src.reset_IBKR_DB paper
python -m src.reset_IBKR_DB test
python -m src.reset_IBKR_DB autom_money
python -m src.reset_IBKR_DB autom_paper

# Mit Table-Prefix
python -m src.reset_IBKR_DB money mike_
python -m src.reset_IBKR_DB money karola_
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
python -m src.reset_IBKR_DB money mike_
python -m src.reset_IBKR_DB paper mike_
```

### Täglicher Lauf (manuell, Schritt für Schritt)
```bash
python -m src.get_flexquery_emails
python -m src.import_ibkr_trades money mike_
python -m src.process_ibkr_trades money mike_
python -m src.xml_append_summary money
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
