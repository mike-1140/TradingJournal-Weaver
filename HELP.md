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

## Account-Zuordnung (Routing)

Die Zuordnung XML/CSV → User + Environment steht in **`src/config.py` → `ACCOUNT_MAP`**.
Key sind die **letzten 4 Ziffern** der IBKR-accountId — funktioniert daher auch mit
maskierten IDs (`U***9360` und `U12369360` ergeben denselben Key).

| accountId endet auf | User | Environment |
|---|---|---|
| 9360 | mike | money |
| 4049 | mike | paper |
| 5466 | mike | autom_money |
| 9254 | mike | autom_paper |
| 8145 | karola | money |

Der Importer liest die accountId aus dem ersten `<FlexStatement>` der XML.
Unbekannte accountIds werden übersprungen (Warnung im Log). Neue Konten müssen
in `ACCOUNT_MAP` ergänzt werden.

**Wichtig — Dateinamen-Filter:** Der Importer verarbeitet nur Dateien, deren Name mit
`flex.` beginnt (`flex.*.xml`, Groß-/Kleinschreibung egal). Manuell erhaltene XMLs vor
dem Import umbenennen, z.B. `K_Echt.xml` → `flex.K_Echt.xml`. Andere Dateien bleiben
unbeachtet in `incoming/` liegen.

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
| `fetch_api` | `src.get_flexquery_api` | Einmal gesamt (derzeit ungenutzt, s.u.) |
| `snapshot_csv` | `src.import_csv_snapshots` | Einmal gesamt (intern pipeline.toml) |
| `snapshot_import` | `src.import_flexquery_snapshot` | Einmal gesamt (intern pipeline.toml) |
| `import` | `src.import_ibkr_trades` | User × Environment |
| `process` | `src.process_ibkr_trades` | Einmal gesamt (intern pipeline.toml) |
| `summary` | `src.xml_append_summary` | Einmal gesamt (intern pipeline.toml) |
| `reset` | `tools.maintenance.reset_IBKR_DB` | User × Environment ⚠️ destruktiv |

Hinweis: Der `import`-Step scannt immer das ganze `incoming/`-Verzeichnis und routet
per accountId — der `--users`-Filter hat auf den Import faktisch keine Wirkung.

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

## get_flexquery_api.py — FlexQuery per Web-API abrufen (derzeit ungenutzt)

Holt FlexQuery-XMLs direkt über die IBKR-Web-API statt per E-Mail.

**Status (2026-07-15): Experiment eingestellt.** IBKR stellt die Daten erst nach dem
EOD-Processing (ca. 14–15 Uhr MEZ) bereit — ein Abruf am Morgen bringt daher keinen
Zeitvorteil gegenüber den Mails. Zusätzlich passt das Dateinamens-Schema der API-Downloads
(`{accountId}_{toDate}_{qid}.xml`) nicht zum `flex.*`-Filter des Importers — solche Dateien
bleiben unbeachtet in `incoming/` liegen (bewusst so belassen).

```bash
python -m src.get_flexquery_api
```

| Variable | Bedeutung |
|---|---|
| `IBKR_FLEX_QUERIES` | Kommagetrennte `token:query_id`-Paare (siehe Docstring im Script) |

---

## import_csv_snapshots.py / import_flexquery_snapshot.py — account_snapshots

Importieren Kontostands-Snapshots in `account_snapshots`:

- `import_csv_snapshots` — aus Activity-CSVs (**empfohlen**, TWRR exakt); Teil der Standard-Pipeline
- `import_flexquery_snapshot` — aus FlexQuery-XMLs (TWRR wird berechnet); Alternative

```bash
# Auto-Modus: alle aktiven Targets aus pipeline.toml
python -m src.import_csv_snapshots
python -m src.import_flexquery_snapshot
```

---

## import_ibkr_trades.py — XML → trades_raw

Scannt `C:\Trade_XML\incoming\` nach `flex.*.xml`-Dateien (andere Dateinamen werden
ignoriert!). Routing erfolgt automatisch per `accountId` aus der XML →
`ACCOUNT_MAP` (in `src/config.py`) → Environment + User + Prefix.
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
Das Script liegt in `tools/maintenance/` (nicht in `src/`).

```bash
# Pflichtargument: Environment; optional: Prefix
python -m tools.maintenance.reset_IBKR_DB money mike_
python -m tools.maintenance.reset_IBKR_DB paper mike_
python -m tools.maintenance.reset_IBKR_DB money karola_
python -m tools.maintenance.reset_IBKR_DB autom_money mike_
python -m tools.maintenance.reset_IBKR_DB autom_paper mike_
```

**Hinweis:** Neue Zusatz-Tabellen werden bewusst **nicht** über reset_IBKR_DB angelegt,
sondern über separate Setup-Scripts in `tools/maintenance/` — z.B.
`setup_psychology_tables.py` (legt die `psychology_*`-Tabellen an, ohne bestehende
Tabellen zu löschen).

**Argumente:**
| Position | Wert | Pflicht |
|---|---|---|
| 1 | Environment | Ja |
| 2 | Table-Prefix | Nein (Standard aus `.env`) |

---

## Typischer Ablauf

### Erster Setup (einmalig)
```bash
python -m tools.maintenance.reset_IBKR_DB money mike_
python -m tools.maintenance.reset_IBKR_DB paper mike_
python -m tools.maintenance.reset_IBKR_DB money karola_
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

### Manuell erhaltene XML importieren (z.B. Karola)
```powershell
# 1. Umbenennen — der Importer verarbeitet nur flex.*.xml
Rename-Item C:\Trade_XML\incoming\K_Echt.xml flex.K_Echt.xml

# 2. Import (Routing per accountId automatisch) + Processing + Summary
python -m src.import_ibkr_trades
python -m src.process_ibkr_trades money karola_
python -m src.xml_append_summary money karola_
```
