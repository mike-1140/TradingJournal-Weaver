# TradingJournal-Weaver

Der Name: Der *Weaver* („Weber“) verwebt die einzelnen Trades aus den IBKR-Berichten zu
Kampagnen, Spreads und P&L-Verläufen.

Import- und Processing-Pipeline für **IBKR Flex-Query-Reports** (XML) und
**Activity Statements** (CSV). Wandelt die IBKR-Rohdaten in ein strukturiertes
Trading-Journal (MySQL) um.

**Offizielle Quelle:** [github.com/mike-1140/TradingJournal-Weaver](https://github.com/mike-1140/TradingJournal-Weaver) —
entwickelt und gepflegt von mike-1140. Forks sind eigenständige Kopien und werden nicht vom Autor betreut.

> **Teil eines Zwei-Repo-Setups:** TradingJournal-Weaver importiert die Rohdaten und verwaltet das
> Datenbankschema. Für eine Weboberfläche zur Auswertung siehe
> [TradingJournal](https://github.com/mike-1140/TradingJournal) (Laravel/Livewire) —
> **TradingJournal-Weaver muss zuerst eingerichtet werden**, TradingJournal zeigt nur an, was hier
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

- **Windows** — andere Betriebssysteme werden derzeit nicht unterstützt (Anleitungen, Hilfsskripte
  und die Ablageordner `C:\Trade_XML\`/`C:\Trade_CSV\` sind auf Windows zugeschnitten)
- Python 3.14
- MySQL (lokal, Port 3306)
- IBKR-Konto mit Flex-Query-Zugriff für echten Datenimport — das `test`-Environment
  funktioniert auch ohne (XML-Dateien manuell einspielen, siehe `pipeline.toml.example`)

> Diese Anleitung beschreibt die lokale Installation. Für einen eigenen Server (Remote-
> Zugriff von mehreren Geräten via VPN) siehe stattdessen
> [`docs/handbuch/technik/70-server-betrieb.md`](docs/handbuch/technik/70-server-betrieb.md).

## Installation

```bash
git clone https://github.com/mike-1140/TradingJournal-Weaver.git
cd TradingJournal-Weaver

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
cp pipeline.toml.example pipeline.toml
cp accounts.toml.example accounts.toml
cp users.toml.example users.toml
```

### .env konfigurieren

Datenbank-Zugangsdaten, `DEFAULT_USER` (Prefix wird aus `users.toml` aufgelöst),
IMAP-Zugang für den Mail-Import, optional `IBKR_FLEX_QUERIES` für den API-Kanal —
Details in den Kommentaren von `.env.example`.

### Datenbank einrichten

```bash
python -m tools.maintenance.reset_IBKR_DB test dein_user_
python -m tools.maintenance.reset_IBKR_DB money dein_user_
```

Destruktiv — legt das Schema aus `sql/` neu an. Pro benötigtem Environment einmal
ausführen (`money`/`paper`/`test`/`autom_money`/`autom_paper`); `test` immer, weil die
Weboberfläche dort startet.

### users.toml konfigurieren

Jeden Benutzer mit seinem Tabellen-Prefix eintragen (z. B. `[dein_user]` → `prefix = "dein_user_"`).
Jeder in `pipeline.toml`/`accounts.toml` genannte Benutzer muss hier stehen, sonst bricht der
Import ab. Lokal, nicht versioniert.

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
get_flexquery_api.py      Flex-Query-Web-API abrufen → C:\Trade_XML\incoming_api\ (zweiter, gleichwertiger Kanal)
import_ibkr_trades.py     incoming_mail\ + incoming_api\ → trades_raw (Routing per accountId → User/Environment)
process_ibkr_trades.py    FIFO-Matching → trades_open / trades_close / trading_campaigns / campaign_ledger
xml_append_summary.py     Summary-XML je User/Environment (für DB-Rebuild)
```

Alles zusammen über den Pipeline-Runner:

```bash
python run_pipeline.py            # Konfiguration: pipeline.toml
```

Datenbanken sichern und wiederherstellen (alle Environments + Laravel-DB, siehe
[Befehlsreferenz](docs/handbuch/technik/30-befehlsreferenz.md)):

```powershell
.\db-backup.ps1                   # Backup nach database\db\
.\db-backup.ps1 -Restore -DryRun  # zeigt die neueste Sicherung je Datenbank
```

## Tests

```bash
pytest
```

## Dokumentation

Die ausführliche Doku ist in zwei Handbücher gegliedert — Übersicht aller Kapitel:
[`docs/handbuch/`](docs/handbuch/README.md). Als PDF zum Herunterladen:
[Vorstellung](https://github.com/mike-1140/TradingJournal/releases/latest/download/TradingJournal-Vorstellung.pdf), [Benutzerhandbuch](https://github.com/mike-1140/TradingJournal/releases/latest/download/TradingJournal-Benutzerhandbuch.pdf) und [Technisches Handbuch](https://github.com/mike-1140/TradingJournal/releases/latest/download/TradingJournal-Technisches-Handbuch.pdf) (jeweils die neueste Version; ältere unter [Releases](https://github.com/mike-1140/TradingJournal/releases)).

| Handbuch | Für wen | Wichtigste Kapitel |
|---|---|---|
| [Benutzerhandbuch](docs/handbuch/README.md#benutzerhandbuch) | Anwender, auch ohne Programmierkenntnisse | [IBKR einrichten](docs/handbuch/benutzer/20-ibkr-einrichten.md), [Windows vorbereiten](docs/handbuch/benutzer/30-windows-vorbereiten.md), [TradingJournal-Weaver installieren](docs/handbuch/benutzer/40-weaver-installieren.md) |
| [Technisches Handbuch](docs/handbuch/README.md#technisches-handbuch) | Technisch Interessierte, Betrieb, Mitwirkende | [Architektur und Import-Pipeline](docs/handbuch/technik/10-architektur-und-pipeline.md), [Aufbau einer Flex Query](docs/handbuch/technik/20-aufbau-flexquery.md), [Befehlsreferenz](docs/handbuch/technik/30-befehlsreferenz.md), [Installation: TradingJournal-Weaver](docs/handbuch/technik/50-installation-weaver.md) |

Weitere Dateien in diesem Repo:

| Datei | Inhalt |
|---|---|
| `CLAUDE.md` | Entwickler-Notizen (Module, Konventionen, bekannte Fixes) |
| `CONTRIBUTING.md` | Wie beitragen — Konventionen, Test-Erwartung, PR-Ablauf |
| `SECURITY.md` | Meldeweg für Sicherheitslücken |
| `LICENSE` | PolyForm Noncommercial 1.0.0 (siehe Abschnitt „Lizenz“) |

## Lizenz

Dieses Projekt steht unter der **[PolyForm Noncommercial License 1.0.0](LICENSE)**. Der Quellcode
ist öffentlich einsehbar („source-available“), aber **nicht** Open Source im Sinne der OSI: Die
Nutzung ist frei für alle nicht-kommerziellen Zwecke, eine kommerzielle Verwertung ist
ausgeschlossen.

**Erlaubt — ohne Rückfrage:**

- Die Software installieren und für die **eigenen privaten Trading-Konten** nutzen — ausdrücklich
  auch für Echtgeld-Konten, auch wenn mit dem Trading selbst Gewinn erzielt werden soll (siehe
  „Additional Permission“ in [`LICENSE`](LICENSE))
- Den Code lesen, daraus lernen, ihn für sich anpassen und erweitern
- Die Software oder eigene Änderungen daran **kostenlos** weitergeben — mit beiliegender
  [`LICENSE`](LICENSE) (inkl. der Zeile `Required Notice: …`)
- Nutzung durch gemeinnützige Organisationen, Schulen, Hochschulen und Forschungseinrichtungen
- Beiträge zu diesem Projekt per Issue oder Pull Request (siehe [`CONTRIBUTING.md`](CONTRIBUTING.md))

**Nicht erlaubt:**

- Die Software oder Teile davon **verkaufen** oder gegen Gebühr anbieten — auch nicht als
  gehosteten Dienst, Abo oder SaaS
- Den Code (oder wesentliche Teile davon) in ein **kommerzielles Produkt** oder eine kommerzielle
  Dienstleistung übernehmen
- Den Einsatz im Rahmen einer bezahlten Tätigkeit für Dritte, z. B. Vermögensverwaltung,
  Trading-Coaching oder Signal-Dienste, bei denen die Software für Kunden genutzt wird
- Die Lizenzhinweise entfernen oder die Software unter einer anderen Lizenz weitergeben

**Kommerzielle Nutzung gewünscht?** Wer das Projekt kommerziell einsetzen möchte, kann über ein
[GitHub-Issue](https://github.com/mike-1140/TradingJournal-Weaver/issues) Kontakt aufnehmen — eine separate Lizenz ist im Einzelfall möglich.

> Diese Zusammenfassung dient der Orientierung. Rechtlich verbindlich ist allein der englische
> Lizenztext in [`LICENSE`](LICENSE).

## Rechtliches

- **Kein Support-Anspruch:** Hobbyprojekt, best effort — keine SLA, keine Garantie auf Reaktionszeit bei Issues oder PRs.
- **Keine Finanzberatung:** Dieses Tool dient ausschließlich der Auswertung und Dokumentation eigener Trades. Es stellt keine Anlage- oder Steuerberatung dar und ersetzt keine professionelle Beratung.
- **Keine Gewährleistung:** Für die Korrektheit der berechneten P&L-, ROI- oder sonstigen Kennzahlen wird keine Haftung übernommen. Vor jeder Nutzung für reale Entscheidungen die Zahlen gegen die eigenen Broker-Unterlagen prüfen.
- **Kein IBKR-Bezug:** Dieses Projekt steht in keiner Verbindung zu und ist nicht autorisiert durch Interactive Brokers LLC. Es verarbeitet lediglich von IBKR bereitgestellte Exportformate (Flex Query/Activity-Statements) sowie die öffentlich dokumentierte Flex-Query-Web-API über die dafür vorgesehenen, offiziellen Schnittstellen.
