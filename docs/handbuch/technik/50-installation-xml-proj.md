# Installation: xml_proj

> Ausführlichere, für Einsteiger geschriebene Version mit mehr Erklärungen:
> [Benutzerhandbuch: xml_proj installieren](../benutzer/40-xml-proj-installieren.md).

Installations- und Erstinitialisierungs-Anleitung für `xml_proj` auf einem neuen Rechner.
Für Befehlsreferenz siehe `docs/handbuch/technik/30-befehlsreferenz.md`, für Architektur/FIFO-Logik/DB-Schema im Detail siehe
`docs/handbuch/technik/10-architektur-und-pipeline.md` (beide im `xml_proj`-Repo).

**Grundlegende Software** (Git, Python, MySQL/MariaDB via XAMPP) muss vorher installiert
sein — siehe [Installation: Windows-Grundausstattung](40-installation-windows.md). Diese Seite setzt das
voraus und beschreibt nur noch die projektspezifische Einrichtung.

---

## Voraussetzungen

| Software | Version | Hinweis |
|---|---|---|
| Python | 3.14 | Bei der Installation "Add python.exe to PATH" aktivieren |
| MySQL/MariaDB Server | via XAMPP | Lokal, Port 3306, laufend und erreichbar; Zugangsdaten mit Recht zum Anlegen neuer Datenbanken — siehe „Installation: Windows-Grundausstattung“ |
| Git | aktuell | Für Clone + Versionsverwaltung |

`shared_python` muss als Sibling-Verzeichnis neben `xml_proj` liegen (`../shared_python`),
da es per editierbarem Install eingebunden wird.

---

## 1. Repository klonen

`xml_proj` hat ein eigenes Git-Repository. Falls schon per [Installation: Windows-Grundausstattung](40-installation-windows.md)
Abschnitt 6 geklont, diesen Schritt überspringen.

```bash
git clone https://github.com/mike-1140/xml_proj.git
cd xml_proj
```

## 2. Virtuelle Umgebung anlegen

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Komfort-Skript für künftige Sitzungen:** `activate.ps1` (im `xml_proj`-Ordner) wechselt
in dieses Verzeichnis und aktiviert die venv in einem Schritt — mit vorangestelltem Punkt
aufrufen, damit es im aktuellen Fenster wirkt, nicht nur im Skript selbst:
```powershell
. .\xml_proj\activate.ps1
```

Falls dabei eine Fehlermeldung wie *"...kann nicht geladen werden, da die Ausführung von
Skripts auf diesem System deaktiviert ist"* kommt (Standardeinstellung auf vielen frischen
Windows-Rechnern): einmalig als Administrator
`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`, danach neues
Terminal öffnen und den Befehl erneut ausführen.

**Desktop-Verknüpfung (optional, einmalig einrichten):** `create-desktop-shortcut.ps1`
(ebenfalls im `xml_proj`-Ordner) legt eine `.lnk`-Verknüpfung auf dem Desktop an, die per
Doppelklick PowerShell öffnet, direkt in `xml_proj` mit aktivierter venv — danach z.B.
sofort `python run_pipeline.py` möglich. Ein `.ps1` selbst startet bei Doppelklick **nicht**
automatisch PowerShell (öffnet sich standardmäßig im Text-Editor), deshalb der Umweg über
eine echte `.lnk`-Verknüpfung:
```powershell
. .\xml_proj\create-desktop-shortcut.ps1
```

## 3. `shared_python` installieren

```bash
pip install -e ../shared_python
```

Stellt `trading_common` bereit (`to_decimal()`, `build_engine()`, Debug-Utilities).
Bei `BackendUnavailable`-Fehlern: `shared_python/pyproject.toml` muss
`build-backend = "setuptools.build_meta"` verwenden (nicht `setuptools.backends.legacy:build`).

## 4. `.env` anlegen

```bash
copy .env.example .env
```

Werte ausfüllen (siehe `.env.example` für alle Felder):

| Variable | Bedeutung |
|---|---|
| `DB_USER` / `DB_PASS` | MySQL-Zugangsdaten |
| `DB_HOST` / `DB_PORT` | Standard: `127.0.0.1` / `3306` |
| `DEFAULT_USER` | Eigener Username (z.B. `dein_user`) — Tabellen-Prefix wird daraus aus `users.toml` aufgelöst. Alternativ direkt `TABLE_PREFIX` setzen (Override) |
| `IMAP_USERNAME` / `IMAP_PASSWORD` / `IMAP_SERVER` | Nur nötig, falls `get_flexquery_emails.py` genutzt wird |
| `IBKR_FLEX_QUERIES` | Optional — nur für den zweiten Import-Kanal `get_flexquery_api.py` |

**Sicherheit:** `.env` ist in `.gitignore` — niemals committen.

**`users.toml`** (im Repo bereits vorhanden, versioniert) ist die zentrale, einzige Quelle
für die User↔Prefix-Zuordnung (`dein_user` → `dein_user_`, `zweiter_user` → `zweiter_user_`) — `DEFAULT_USER`
oben, `ACCOUNT_MAP` in `config.py` und `pipeline.toml` (Schritt 6) lösen den Prefix alle von
dort auf. Nur bei einem komplett **neuen** User nötig, dort einen Eintrag zu ergänzen.

Die `DB_NAME_*`-Variablen (`ibkr_money`, `ibkr_paper`, `ibkr_test`, `ibkr_autom_money`,
`ibkr_autom_paper`) müssen normalerweise nicht angepasst werden — sie legen die
tatsächlichen MySQL-Datenbanknamen fest und werden von TradingJournal (`config/database.php`)
in gleicher Form erwartet.

## 5. Datenbanken initialisieren

⚠️ **Destruktiv** — legt Datenbank + alle Tabellen aus `sql/` neu an, löscht bestehende Daten
des jeweiligen Environment/Prefix-Paars. Nur beim ersten Setup bzw. bewusstem Reset ausführen.

Für jede benötigte Kombination aus Environment × Nutzer-Prefix einmal ausführen:

```bash
python -m tools.maintenance.reset_IBKR_DB money dein_user_
python -m tools.maintenance.reset_IBKR_DB paper dein_user_
python -m tools.maintenance.reset_IBKR_DB test dein_user_
```

Zusätzliche Tabellen außerhalb des Kern-Schemas (z.B. Psychology-Modul) werden **nicht**
über `reset_IBKR_DB.py` angelegt, sondern über eigene Setup-Scripts in
`tools/maintenance/`, damit ein Reset nicht versehentlich fachfremde Tabellen mitlöscht:

```bash
python -m tools.maintenance.setup_psychology_tables money dein_user_
```

**Für einen zusätzlichen, weiteren User** (z.B. ein Familienmitglied, nachdem die
Grundinstallation schon steht): diesen Schritt mit dem neuen Prefix wiederholen (`users.toml`
ggf. vorher um den neuen User ergänzen, siehe Schritt 4), danach den passenden Laravel-User
anlegen (siehe TradingJournal-Setup-Anleitung, Schritt 5) — **mit demselben Prefix** auf
beiden Seiten.

## 6. `pipeline.toml` anlegen

```bash
copy pipeline.toml.example pipeline.toml
```

`pipeline.toml` ist **maschinenspezifisch** und daher wie `.env` in `.gitignore` (nicht
versioniert) — jede Maschine trägt hier nur die User/Environments ein, die auf **ihr**
tatsächlich per Schritt 5 initialisiert wurden. Ein Eintrag für einen User, dessen Tabellen
auf dieser Maschine nicht existieren, lässt `run_pipeline.py` im Auto-Modus mit
"Tabelle nicht gefunden" fehlschlagen.

```toml
[users.dein_user]
environments = ["money"]   # nur die Environments, die in Schritt 5 initialisiert wurden
```

Kein `prefix =` nötig — der wird automatisch aus `users.toml` aufgelöst (User-Name = Name
der Sektion, hier `dein_user`). Nur falls ein User (noch) nicht in `users.toml` steht, hier per
`prefix = "..."` explizit setzen.

## 7. Ersten Lauf testen

```bash
python run_pipeline.py --dry-run
```

Zeigt alle konfigurierten Steps/Befehle laut `pipeline.toml`, ohne etwas auszuführen.
Danach für einen echten Testlauf (User-/Env-Namen an die eigene `pipeline.toml` anpassen):

```bash
python run_pipeline.py --users dein_user --envs test
```

---

## Weiterführende Dokumentation

| Datei | Inhalt |
|---|---|
| `docs/handbuch/technik/30-befehlsreferenz.md` | Vollständige Befehlsreferenz aller Scripts |
| `docs/handbuch/technik/10-architektur-und-pipeline.md` | Architektur, FIFO-Logik, DB-Schema im Detail |
| [TradingJournal-Setup](60-installation-tradingjournal.md) | Setup der Laravel-UI (liest dieselben Datenbanken) |
