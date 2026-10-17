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

Jeder User hat einen eigenen Tabellen-Prefix, zentral definiert in **`users.toml`**
(einzige Quelle — `config.py` und `pipeline.toml` lösen den Prefix von dort auf):

| User | Prefix |
|---|---|
| dein_user | `dein_user_` |
| zweiter_user | `zweiter_user_` |

Beispiel: Prefix `dein_user_` → Tabellen `dein_user_trades_raw`, `dein_user_trades_open`, ...

Für manuelle Einzelaufrufe ohne CLI-Prefix-Argument: `.env` → `DEFAULT_USER=<name>` (Prefix
wird aus `users.toml` aufgelöst) oder direkt `TABLE_PREFIX=<prefix>` (Override, gewinnt
falls beides gesetzt ist).

## Account-Zuordnung (Routing)

Die Zuordnung XML/CSV → User + Environment steht in **`accounts.toml`** (nicht
versioniert, wie `pipeline.toml` — Vorlage: `accounts.toml.example`), aufgelöst über
`src/config.py` → `get_account_config()`. Key sind die **letzten 4 Ziffern** der
IBKR-accountId — funktioniert daher auch mit maskierten IDs (`U***1234` und
`U12341234` ergeben denselben Key).

```toml
[1234]
user = "dein_user"
environment = "money"
```

Der Importer liest die accountId aus dem ersten `<FlexStatement>` der XML.
Unbekannte accountIds werden übersprungen (Warnung im Log). Neue Konten müssen
in `accounts.toml` ergänzt werden.

**Kein Dateinamen-Filter mehr (Normalbetrieb):** Der Importer verarbeitet alle `*.xml`-Dateien
in `incoming_mail\` und `incoming_api\` gleichwertig — die Quelle (Mail vs. FlexQuery-API)
ist irrelevant, Checksum-Dedup (tradeID+dateTime+symbol+qty+price) verhindert doppelte Trades,
falls dieselben Daten über beide Kanäle ankommen. Einzige Ausnahme: der dedizierte
**TEST-Modus** verlangt weiterhin das Muster `flex.*.xml` (siehe [TEST-Environment](#test-environment--manuelle-xmls-automatisch-erkennen)).

## Verzeichnisstruktur (XML-Dateien)

```
C:\Trade_XML\
  incoming_mail\                ← eingehende XML-Dateien per E-Mail (accountId-Routing)
  incoming_api\                 ← eingehende XML-Dateien per FlexQuery Web-API (accountId-Routing)
  <env>\
    <user>\
      processed\               ← erfolgreich importierte Dateien (aus beiden Quellen)
      deleted\                 ← Dateien ohne neue Trades
    summary_<prefix><env>.xml  ← zusammengefasste Summary
  test\
    <user>\
      incoming\                ← manuell abgelegte Test-XMLs (flex.*.xml), kein accountId-Routing
      processed\
      deleted\
C:\Trade_CSV\
  incoming\                    ← eingehende Activity-CSVs (nur per Mail, kein API-Äquivalent)
    <user>\
      processed\               ← erfolgreich importierte CSVs
```

Der `test\<user>\`-Ordner existiert nur für User mit einem `[[test]]`-Eintrag in
`pipeline.toml` (siehe [TEST-Environment](#test-environment--manuelle-xmls-automatisch-erkennen)).

---

## TEST-Environment — manuelle XMLs automatisch erkennen

Für TEST gibt es kein echtes IBKR-Konto, also auch keinen `accounts.toml`-Eintrag —
Environment und Prefix werden stattdessen durch das **Verzeichnis** bestimmt, nicht
durch die accountId in der XML. Kein Umbenennen der accountId, kein manuelles
Patchen der XML nötig.

**Konfiguration in `pipeline.toml`:** Ein `[[test]]`-Eintrag pro User — kein
`enabled`-Schalter, ein vorhandener Eintrag ist automatisch aktiv:

```toml
[[test]]
user = "dein_user"

[[test]]
user = "zweiter_user"
```

Zum Deaktivieren einfach den Eintrag aus der TOML entfernen/auskommentieren.

**Workflow:**

```powershell
# 1. Datei muss dem flex.*.xml-Muster entsprechen (nur im TEST-Modus noch Pflicht)
Rename-Item C:\Trade_XML\incoming_mail\meine_datei.xml flex.meine_datei.xml

# 2. In den passenden User-Ordner legen — kein incoming_mail/incoming_api der Hauptroute!
Move-Item flex.meine_datei.xml C:\Trade_XML\test\dein_user\incoming\
```

```bash
# 3. Ganz normal laufen lassen — TEST wird automatisch mit erfasst
python run_pipeline.py
# oder einzeln:
python -m src.import_ibkr_trades
python -m src.process_ibkr_trades
```

`import_ibkr_trades.py` scannt bei jedem Auto-Lauf zusätzlich zum normalen
accountId-Routing alle `[[test]]`-Ordner (`C:\Trade_XML\test\<user>\incoming\`) und
importiert sie direkt mit dem konfigurierten Prefix in die TEST-DB. `process_ibkr_trades.py`
verarbeitet TEST im Auto-Modus automatisch mit, da es ebenfalls `load_active_targets()`
aus `pipeline.toml` liest.

**Kein Summary für TEST:** `xml_append_summary.py` lässt TEST im Auto-Modus bewusst aus
— Testdaten brauchen kein Summary-Replay, sie lassen sich jederzeit erneut importieren.
Ein `summary_<prefix>test.xml` entsteht daher nicht automatisch (nur bei explizitem
CLI-Aufruf `python -m src.xml_append_summary test dein_user_`).

**Alternative — Einzeldatei manuell testen, ohne pipeline.toml-Eintrag:**
```bash
# Datei liegt in C:\Trade_XML\incoming_mail\ (Hauptordner), Prefix explizit angeben
python -m src.import_ibkr_trades test dein_user_
python -m src.process_ibkr_trades test dein_user_
```
Ohne Prefix-Argument wird der erste `[[test]]`-Eintrag aus `pipeline.toml` verwendet,
sonst `TABLE_PREFIX` aus `.env`. Dieser Modus scannt den **Hauptordner** `incoming_mail\`
(nicht `test\<user>\incoming\`, nicht `incoming_api\`) und ignoriert die accountId komplett.

**Neu testen mit derselben Datei:** Der Checksum-Schutz verhindert Doppel-Import
(`0 Trades importiert` ist dann erwartetes Verhalten, kein Fehler). Für einen sauberen
Neustart die TEST-DB des Prefixes zurücksetzen (⚠️ löscht alle bisherigen TEST-Daten
dieses Prefixes):
```bash
python -m tools.maintenance.reset_IBKR_DB test dein_user_
```

---

## run_pipeline.py — Vollständiger Pipeline-Runner

Konfiguration in `pipeline.toml`. Führt alle Steps automatisch aus.

```bash
# Alles ausführen (laut pipeline.toml)
python run_pipeline.py

# Nur bestimmte User
python run_pipeline.py --users mike
python run_pipeline.py --users dein_user zweiter_user

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
| `fetch_api` | `src.get_flexquery_api` | Einmal gesamt |
| `snapshot_csv` | `src.import_csv_snapshots` | Einmal gesamt (intern pipeline.toml) |
| `import` | `src.import_ibkr_trades` | Ohne `--users`/`--envs`: einmal gesamt. Mit Filter: pro passendem User × Environment |
| `process` | `src.process_ibkr_trades` | Einmal gesamt (intern pipeline.toml) |
| `summary` | `src.xml_append_summary` | Einmal gesamt (intern pipeline.toml) |
| `reset` | `tools.maintenance.reset_IBKR_DB` | User × Environment ⚠️ destruktiv |

`import_ibkr_trades.py` unterstützt seit Kurzem ein CLI-Override `<env> <prefix>`
(analog `process_ibkr_trades.py`) — nur Dateien dieses einen Ziels werden importiert,
alle anderen bleiben unangetastet liegen. `run_pipeline.py` nutzt das automatisch:
ohne `--users`/`--envs` läuft `import` einmal global (effizient, accountId routet
intern), mit gesetztem Filter läuft es pro passendem User × Environment.

**`account_snapshots` kommt ausschließlich aus dem Kontoauszug (Activity Statement, CSV per
Mail) über `snapshot_csv`.** Den Kontoauszug gibt es nicht per Web-API, und die FlexQueries
(Mail wie API) enthalten keine Snapshot-Sektionen (EquitySummary, CashReport, MTM)
(geprüft 2026-10-17: keine der 763 FlexQuery-XMLs aus Mail- und API-Kanal enthält Snapshot-Sektionen). Der frühere Step `snapshot_import`
(`import_flexquery_snapshot.py`, Snapshots aus FlexQuery-XMLs) wurde deshalb am 2026-10-17
entfernt.

---

## get_flexquery_emails.py — E-Mails abrufen

Lädt IBKR FlexQuery XML- und Activity-CSV-Anhänge aus dem Mail-Postfach und speichert
sie in `C:\Trade_XML\incoming_mail\` bzw. `C:\Trade_CSV\incoming\`. Routing (welcher User /
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

## get_flexquery_api.py — FlexQuery per Web-API abrufen

Holt FlexQuery-XMLs direkt über die IBKR-Web-API, **parallel** zur Mail-Pipeline
(`get_flexquery_emails.py`) — beide Kanäle sind gleichwertig aktiv, kein reiner
Verifikationskanal mehr. Schreibt nach `C:\Trade_XML\incoming_api\` (getrennt von
`incoming_mail\`, damit beide Quellen unabhängig nachvollziehbar bleiben). Der
`import`-Step scannt **beide** Ordner und importiert daraus `trades_raw` — die
Query liefert dieselben Trades wie die Mail-XML, Checksum-Dedup verhindert
doppelte Einträge. Mit denselben Sektionen eingerichtet wie die Mail-Query
(Trades, Option Exercises/Assignments/Expirations, Corporate Actions) liefert die
API-Query auch Assignment-/Expiry-Events und Splits — vollwertiger zweiter Kanal.

Timing: Der Report wird bei Anfrage **on-demand generiert**, kein fixes Tages-Zeitfenster
(die frühere Annahme "erst ab ca. 14–15 Uhr MEZ" war falsch). Voraussetzung ist nur, dass
der Börsentag abgeschlossen ist — funktioniert bereits kurz nach Handelsschluss zuverlässig
(bestätigt: erfolgreicher Lauf 2026-08-06 um 06:01 Uhr lokal). Die Retry-Logik
(`RETRY_DELAY`/`MAX_RETRIES`) fängt die kurze "noch in Verarbeitung"-Phase ab — typischerweise
wenige Sekunden, bis zu ~30s bei Accounts mit geringerer IBKR-Priorität (z.B. Paper-Konten).

```bash
python -m src.get_flexquery_api
```

| Variable | Bedeutung |
|---|---|
| `IBKR_FLEX_QUERIES` | Kommagetrennte `token:query_id`-Paare (siehe Docstring im Script) |

Ohne `IBKR_FLEX_QUERIES` in `.env` ist der Schritt ein No-Op (kein Fehler, Exit-Code 0) —
kann also gefahrlos im Standard-Pipeline-Lauf aktiv bleiben, auch wenn (noch) nicht für
alle Accounts ein Token/Query konfiguriert ist.

---

## import_csv_snapshots.py — account_snapshots

Importieren Kontostands-Snapshots in `account_snapshots`:

- `import_csv_snapshots` — aus den Activity-CSVs (Kontoauszug per Mail, **einzige Quelle**,
  TWRR exakt); Teil der Standard-Pipeline (`snapshot_csv`)

```bash
# Auto-Modus: alle aktiven Targets aus pipeline.toml
python -m src.import_csv_snapshots
```

**Achtung:** Cash-Positionen werden fest auf EUR + USD verdrahtet erfasst (`cash_eur`/`cash_usd`
in `sql/account_snapshots.sql`, der CSV-Parser sucht explizit nach diesen zwei Währungen). Cash in einer
dritten Währung wird stillschweigend nicht importiert. Details + Begründung: `docs/pipeline-workflow.md` § 8.2 `account_snapshots`.

---

## import_ibkr_trades.py — XML → trades_raw

Scannt `C:\Trade_XML\incoming_mail\` **und** `C:\Trade_XML\incoming_api\` nach
`*.xml`-Dateien (kein Dateinamen-Filter im Normalbetrieb). Routing erfolgt automatisch
per `accountId` aus der XML → `accounts.toml` (via `src/config.py::get_account_config()`) → Environment + User +
Prefix. Verarbeitete Dateien landen in `C:\Trade_XML\<env>\<user>\processed\` (aus
beiden Quellordnern gleichermaßen).

```bash
# Auto-Modus: scannt beide incoming-Ordner, Routing per accountId (kein Argument nötig)
python -m src.import_ibkr_trades

# CLI-Override: nur ein Environment/Prefix importieren, alles andere bleibt liegen
python -m src.import_ibkr_trades money dein_user_
python -m src.import_ibkr_trades paper dein_user_

# Aus summary.xml importieren (explizites Environment + Prefix erforderlich)
python -m src.import_ibkr_trades from_summary money dein_user_
python -m src.import_ibkr_trades from_summary money zweiter_user_
python -m src.import_ibkr_trades from_summary autom_paper dein_user_
```

**Argumente:**
| Position | Wert | Pflicht |
|---|---|---|
| 1 | Environment (CLI-Override) oder `from_summary` oder `test` | Nein — ohne Argument: Auto-Modus |
| 2 | Table-Prefix (z.B. `dein_user_`) | Bei CLI-Override/`from_summary`: Ja. Sonst optional/Standard aus `.env` |
| 3 | `from_summary` | Nur im from_summary-Modus, an letzter Position |

Bei CLI-Override (`<env> <prefix>`) werden Dateien anderer Environments/Prefixe in
beiden Ordnern übersprungen und bleiben liegen — für den nächsten Lauf ohne Filter
oder mit anderem Ziel.

---

## process_ibkr_trades.py — trades_raw → trades_open / trades_close

Verarbeitet unverarbeitete Einträge aus `trades_raw` per FIFO-Matching.
Schreibt Ergebnisse in `trades_open`, `trades_close`, `trading_campaigns`, `campaign_ledger`.

```bash
# Auto-Modus: alle aktiven Targets aus pipeline.toml (kein Argument nötig)
python -m src.process_ibkr_trades

# CLI-Override: explizites Environment (überschreibt pipeline.toml)
python -m src.process_ibkr_trades money
python -m src.process_ibkr_trades money dein_user_
python -m src.process_ibkr_trades money zweiter_user_
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

**⚠️ Bekannte Lücke:** Der `flex.`-Präfix-Filter (`FLEX_FILE_PREFIX` in
`xml_append_summary.py`) erfasst nur Mail-Dateien. Dateien aus `incoming_api\`
(anderes Namensschema, z.B. `U12109360_..._api_8_0870.xml`) landen zwar korrekt in
`trades_raw` und in `processed/`, werden aber vom Summary-Builder ignoriert. Betrifft
nur den Sonderfall, dass an einem Tag ausschließlich der API-Kanal Daten liefert (Mail
fiel aus) — die Trades sind in der DB vorhanden, fehlen aber bei einem künftigen
`from_summary`-Rebuild. Noch nicht behoben.

```bash
# Auto-Modus: alle aktiven Targets aus pipeline.toml (kein Argument nötig)
python -m src.xml_append_summary

# CLI-Override: explizites Environment + Prefix (überschreibt pipeline.toml)
python -m src.xml_append_summary money dein_user_
python -m src.xml_append_summary paper dein_user_
python -m src.xml_append_summary autom_money dein_user_
python -m src.xml_append_summary money zweiter_user_
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
python -m tools.maintenance.reset_IBKR_DB money dein_user_
python -m tools.maintenance.reset_IBKR_DB paper dein_user_
python -m tools.maintenance.reset_IBKR_DB money zweiter_user_
python -m tools.maintenance.reset_IBKR_DB autom_money dein_user_
python -m tools.maintenance.reset_IBKR_DB autom_paper dein_user_
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
python -m tools.maintenance.reset_IBKR_DB money dein_user_
python -m tools.maintenance.reset_IBKR_DB paper dein_user_
python -m tools.maintenance.reset_IBKR_DB money zweiter_user_
```

### Täglicher Lauf (automatisch, alle User/Envs laut pipeline.toml)
```bash
python run_pipeline.py
```

### Täglicher Lauf (manuell, Schritt für Schritt)
```bash
python -m src.get_flexquery_emails       # Mails holen → incoming_mail/
python -m src.get_flexquery_api          # FlexQuery-API holen → incoming_api/
python -m src.import_ibkr_trades         # XML importieren (auto-routing per accountId, beide Ordner)
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

### Nur ein Environment importieren (CLI-Override, seit run_pipeline-Update)
```bash
python run_pipeline.py --steps import --envs money
# entspricht intern: python -m src.import_ibkr_trades money dein_user_
#                     python -m src.import_ibkr_trades money zweiter_user_
```

### Einzelnen Account aus summary.xml neu importieren
```bash
python -m src.import_ibkr_trades from_summary money dein_user_
python -m src.process_ibkr_trades money dein_user_
```

### Manuell erhaltene XML importieren (z.B. Karola)
```powershell
# Einfach ablegen — kein Umbenennen mehr noetig (kein Dateinamen-Filter im Normalbetrieb)
Move-Item K_Echt.xml C:\Trade_XML\incoming_mail\
```
```bash
# Import (Routing per accountId automatisch) + Processing + Summary
python -m src.import_ibkr_trades
python -m src.process_ibkr_trades money zweiter_user_
python -m src.xml_append_summary money zweiter_user_
```

### XML schnell im TEST-Environment testen
Siehe [TEST-Environment](#test-environment--manuelle-xmls-automatisch-erkennen) für Details.
```powershell
Rename-Item C:\Trade_XML\incoming_mail\meine_datei.xml flex.meine_datei.xml
Move-Item C:\Trade_XML\incoming_mail\flex.meine_datei.xml C:\Trade_XML\test\dein_user\incoming\
```
```bash
python run_pipeline.py
```
