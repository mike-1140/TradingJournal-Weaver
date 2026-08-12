# Trading Journal 3.0 — xml_proj

Import- und Processing-Pipeline für **IBKR FlexQuery-Reports** (XML) und
**Activity Statements** (CSV). Wandelt die IBKR-Rohdaten in ein strukturiertes
Trading-Journal (MySQL) um.

> **Teil eines Zwei-Repo-Setups:** xml_proj importiert die Rohdaten und verwaltet das
> Datenbankschema. Für eine Web-Oberfläche zur Auswertung siehe
> [TradingJournal](https://github.com/mike-1140/TradingJournal) (Laravel/Livewire) —
> **xml_proj muss zuerst eingerichtet werden**, TradingJournal zeigt nur an, was hier
> bereits in der Datenbank steht.

## Features

- FIFO-Lot-Matching für Aktien, Optionen und FX
- Kampagnen-Tracking je Symbol (ACTIVE → PENDING → CLOSED)
- Options-Strategie-Erkennung (Spreads, Iron Condors, Straddles, …)
- Vollständiger Audit-Trail im `campaign_ledger` (inkl. Running Balance)
- Multi-User (Tabellen-Prefix) und Multi-Environment (money / paper / test / autom_*)

## Stack

- **Sprache:** Python 3.14
- **Datenbank:** MySQL (SQLAlchemy + PyMySQL)
- **Datenverarbeitung:** pandas, numpy
- **Optionales Dashboard:** Streamlit (`display_xml_data.py`)

## Voraussetzungen

- Python 3.14
- MySQL (lokal, Port 3306)
- IBKR-Konto mit FlexQuery-Zugriff für echten Datenimport — das `test`-Environment
  funktioniert auch ohne (XML-Dateien manuell einspielen, siehe `pipeline.toml.example`)

## Installation

```bash
git clone https://github.com/mike-1140/xml_proj.git
cd xml_proj

python -m venv .venv
.venv\Scripts\activate       # Windows; unter Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
cp pipeline.toml.example pipeline.toml
cp accounts.toml.example accounts.toml
```

### .env konfigurieren

Datenbank-Zugangsdaten, `DEFAULT_USER` (Prefix wird aus `users.toml` aufgelöst),
IMAP-Zugang für den Mail-Import, optional `IBKR_FLEX_QUERIES` für den API-Kanal —
Details in den Kommentaren von `.env.example`.

### Datenbank einrichten

```bash
python -m tools.maintenance.reset_IBKR_DB money dein_user_
```

Destruktiv — legt das Schema aus `sql/` neu an. Pro benötigtem Environment einmal
ausführen (`money`/`paper`/`test`/`autom_money`/`autom_paper`).

### pipeline.toml konfigurieren

Eigenen User (aus `users.toml`) und die auf dieser Maschine initialisierten Environments
eintragen — Details in den Kommentaren der kopierten Vorlage.

### accounts.toml konfigurieren

Eigene IBKR-accountId(s) → User/Environment eintragen (Key = letzte 4 Ziffern der
accountId, funktioniert auch mit maskierten IDs) — Details in den Kommentaren der
kopierten Vorlage. Enthält reale Kontodaten, daher wie `pipeline.toml` nicht versioniert.

## Ablauf (Kurzfassung)

```
get_flexquery_emails.py   IBKR-Mails abrufen → C:\Trade_XML\incoming_mail\ + C:\Trade_CSV\incoming\
get_flexquery_api.py      FlexQuery Web-API abrufen → C:\Trade_XML\incoming_api\ (zweiter, gleichwertiger Kanal)
import_ibkr_trades.py     incoming_mail\ + incoming_api\ → trades_raw (Routing per accountId → User/Environment)
process_ibkr_trades.py    FIFO-Matching → trades_open / trades_close / trading_campaigns / campaign_ledger
xml_append_summary.py     Summary-XML je User/Environment (für DB-Rebuild)
```

Alles zusammen über den Pipeline-Runner:

```bash
python run_pipeline.py            # Konfiguration: pipeline.toml
```

## Tests

```bash
pytest
```

## Dokumentation

| Datei | Inhalt |
|---|---|
| `HELP.md` | Befehlsreferenz aller Scripts (Argumente, Beispiele, typische Abläufe) |
| `docs/pipeline-workflow.md` | Technische Gesamtdokumentation (Architektur, FIFO-Logik, DB-Schema) |
| `docs/setup/windows-prerequisites(-einsteiger).md` | Grundausstattung (Git, XAMPP, Composer, Node.js, Python) — auch für TradingJournal |
| `docs/setup/xml_proj-setup(-einsteiger).md` | Setup-Anleitung für dieses Repo, technisch bzw. für Einsteiger |
| `CLAUDE.md` | Entwickler-Notizen (Module, Konventionen, bekannte Fixes) |
| `CONTRIBUTING.md` | Wie beitragen — Konventionen, Test-Erwartung, PR-Ablauf |
| `SECURITY.md` | Meldeweg für Sicherheitslücken |
| `LICENSE` | MIT |

## Rechtliches

- **Lizenz:** MIT, siehe [`LICENSE`](LICENSE).
- **Kein Support-Anspruch:** Hobbyprojekt, best effort — keine SLA, keine Garantie auf Reaktionszeit bei Issues oder PRs.
- **Keine Finanzberatung:** Dieses Tool dient ausschließlich der Auswertung und Dokumentation eigener Trades. Es stellt keine Anlage- oder Steuerberatung dar und ersetzt keine professionelle Beratung.
- **Keine Gewährleistung:** Für die Korrektheit der berechneten P&L-, ROI- oder sonstigen Kennzahlen wird keine Haftung übernommen. Vor jeder Nutzung für reale Entscheidungen die Zahlen gegen die eigenen Broker-Unterlagen prüfen.
- **Kein IBKR-Bezug:** Dieses Projekt steht in keiner Verbindung zu und ist nicht autorisiert durch Interactive Brokers LLC. Es verarbeitet lediglich von IBKR bereitgestellte Exportformate (FlexQuery/Activity-Statements) sowie die öffentlich dokumentierte FlexQuery-Web-API über die dafür vorgesehenen, offiziellen Schnittstellen.
