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

## Verzeichnisstruktur (XML-Dateien)

```
C:\Trade_XML\
  incoming\                    ← alle eingehenden XML-Dateien (accountId-Routing)
  <env>\
    <user>\
      processed\               ← erfolgreich importierte Dateien
      deleted\                 ← Dateien ohne neue Trades
    summary_<prefix><env>.xml  ← zusammengefasste Summary
C:\Trade_CSV\
  incoming\                    ← eingehende Activity-CSVs
    <user>\
      processed\               ← erfolgreich importierte CSVs
```

---

## run_pipeline.py — Vollständiger Pipeline-Runner

Konfiguration in `pipeline.toml`. Führt alle Steps automatisch aus.

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
| `process` | `src.process_ibkr_trades` | Einmal gesamt (intern pipeline.toml) |
| `summary` | `src.xml_append_summary` | Einmal gesamt (intern pipeline.toml) |
| `reset` | `src.reset_IBKR_DB` | User × Environment ⚠️ destruktiv |

---

## get_flexquery_emails.py — E-Mails abrufen

Lädt IBKR FlexQuery XML- und Activity-CSV-Anhänge aus dem Mail-Postfach und speichert
sie in `C:\Trade_XML\incoming\` bzw. `C:\Trade_CSV\incoming\`. Routing (welcher User /
welches Environment) erfolgt erst beim Import per accountId.

```bash
python -m src.get_flexquery_emails
```

Keine Argumente. Relevante `.env`-Variablen:

| Variable | Bedeutung |
|---|---|
| `IMAP_USERNAME` | Mail-Adresse |
| `IMAP_PASSWORD` | Mail-Passwort |
| `IMAP_SERVER` | IMAP-Server (Standard: `imap.gmx.com`) |
| `IBKR_ACTIVITY_SUBJECT` | Betreff Activity Statement EN (Standard: `Activity Statement`) |
| `IBKR_ACTIVITY_SUBJECT_DE` | Betreff Activity Statement DE (Standard: `Kontoauszug`) |

---

## import_ibkr_trades.py — XML → trades_raw

Scannt `C:\Trade_XML\incoming\` nach `flex.*.xml`-Dateien. Routing erfolgt automatisch
per `accountId` aus der XML → `ACCOUNT_MAP` → Environment + User + Prefix.
Verarbeitete Dateien landen in `C:\Trade_XML\<env>\<user>\processed\`.

```bash
# Auto-Modus: scannt incoming/, Routing per accountId (kein Argument nötig)
python -m src.import_ibkr_trades

# Aus summary.xml importieren (explizites Environment + Prefix erforderlich)
python -m src.import_ibkr_trades from_summary money mike_
python -m src.import_ibkr_trades from_summary money karola_
python -m src.import_ibkr_trades from_summary autom_paper mike_
```

**Argumente (nur für `from_summary`):**
| Position | Wert | Pflicht |
|---|---|---|
| 1 | `from_summary` | Ja (schaltet Modus um) |
| 2 | Environment | Ja |
| 3 | Table-Prefix (z.B. `mike_`) | Ja |

---

## process_ibkr_trades.py — trades_raw → trades_open / trades_close

Verarbeitet unverarbeitete Einträge aus `trades_raw` per FIFO-Matching.
Schreibt Ergebnisse in `trades_open`, `trades_close`, `trading_campaigns`, `campaign_ledger`.

```bash
# Auto-Modus: alle aktiven Targets aus pipeline.toml (kein Argument nötig)
python -m src.process_ibkr_trades

# CLI-Override: explizites Environment (überschreibt pipeline.toml)
python -m src.process_ibkr_trades money
python -m src.process_ibkr_trades money mike_
python -m src.process_ibkr_trades money karola_
```

**Argumente (CLI-Override):**
| Position | Wert | Pflicht |
|---|---|---|
| 1 | Environment | Ja (für CLI-Override) |
| 2 | Table-Prefix | Nein (Standard aus `.env`) |

---

## xml_append_summary.py — Einzel-XMLs zu summary.xml zusammenfassen

Liest neue `flex.*.xml`-Dateien aus `<env>/<user>/processed/` und aktualisiert
`summary_<prefix><env>.xml`. Keine Duplikate (fromDate eindeutig), aufsteigende
Reihenfolge, Performance-Cache.

```bash
# Auto-Modus: alle aktiven Targets aus pipeline.toml (kein Argument nötig)
python -m src.xml_append_summary

# CLI-Override: explizites Environment + Prefix (überschreibt pipeline.toml)
python -m src.xml_append_summary money mike_
python -m src.xml_append_summary paper mike_
python -m src.xml_append_summary autom_money mike_
python -m src.xml_append_summary money karola_
```

**Argumente (CLI-Override):**
| Position | Wert | Pflicht |
|---|---|---|
| 1 | Environment | Ja (für CLI-Override) |
| 2 | Table-Prefix | Ja (für CLI-Override) |

---

## reset_IBKR_DB.py — Datenbank initialisieren

Legt die Datenbank und alle Tabellen neu an (aus `sql/`-Schemas).
**Achtung: Löscht alle bestehenden Daten!** Nur beim ersten Setup oder nach Reset verwenden.

```bash
# Pflichtargument: Environment + Prefix
python -m src.reset_IBKR_DB money mike_
python -m src.reset_IBKR_DB paper mike_
python -m src.reset_IBKR_DB money karola_
python -m src.reset_IBKR_DB autom_money mike_
python -m src.reset_IBKR_DB autom_paper mike_
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
python -m src.reset_IBKR_DB money karola_
```

### Täglicher Lauf (automatisch, alle User/Envs laut pipeline.toml)
```bash
python run_pipeline.py
```

### Täglicher Lauf (manuell, Schritt für Schritt)
```bash
python -m src.get_flexquery_emails       # Mails holen → incoming/
python -m src.import_ibkr_trades         # XML importieren (auto-routing per accountId)
python -m src.process_ibkr_trades        # FIFO-Verarbeitung (alle Targets)
python -m src.xml_append_summary         # Summary aktualisieren (alle Targets)
```

### Nur einen User neu verarbeiten
```bash
python run_pipeline.py --users mike --steps process
```

### Nur Emails holen und importieren
```bash
python run_pipeline.py --steps fetch_emails import
```

### Einzelnen Account aus summary.xml neu importieren
```bash
python -m src.import_ibkr_trades from_summary money mike_
python -m src.process_ibkr_trades money mike_
```
