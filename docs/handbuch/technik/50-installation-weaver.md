# Installation: TradingJournal-Weaver

> Ausführlichere, für Einsteiger geschriebene Version mit mehr Erklärungen:
> [Benutzerhandbuch: TradingJournal-Weaver installieren](../benutzer/40-weaver-installieren.md).

Installations- und Erstinitialisierungs-Anleitung für `TradingJournal-Weaver` auf einem neuen Rechner.
Für Befehlsreferenz siehe `docs/handbuch/technik/30-befehlsreferenz.md`, für Architektur/FIFO-Logik/DB-Schema im Detail siehe
`docs/handbuch/technik/10-architektur-und-pipeline.md` (beide im `TradingJournal-Weaver`-Repo).

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

---

## 1. Repository klonen

`TradingJournal-Weaver` hat ein eigenes Git-Repository. Falls schon per [Installation: Windows-Grundausstattung](40-installation-windows.md)
Abschnitt 6 geklont, diesen Schritt überspringen.

```bash
git clone https://github.com/mike-1140/TradingJournal-Weaver.git
cd TradingJournal-Weaver
```

## 2. Virtuelle Umgebung anlegen

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Komfort-Skript für künftige Sitzungen:** `activate.ps1` (im `TradingJournal-Weaver`-Ordner) wechselt
in dieses Verzeichnis und aktiviert die venv in einem Schritt — mit vorangestelltem Punkt
aufrufen, damit es im aktuellen Fenster wirkt, nicht nur im Skript selbst:
```powershell
. .\TradingJournal-Weaver\activate.ps1
```

Falls dabei eine Fehlermeldung wie *"...kann nicht geladen werden, da die Ausführung von
Skripts auf diesem System deaktiviert ist"* kommt (Standardeinstellung auf vielen frischen
Windows-Rechnern): einmalig als Administrator
`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`, danach neues
Terminal öffnen und den Befehl erneut ausführen.

**Desktop-Verknüpfung (optional, einmalig einrichten):** `create-desktop-shortcut.ps1`
(ebenfalls im `TradingJournal-Weaver`-Ordner) legt eine `.lnk`-Verknüpfung auf dem Desktop an, die per
Doppelklick PowerShell öffnet, direkt in `TradingJournal-Weaver` mit aktivierter venv — danach z.B.
sofort `python run_pipeline.py` möglich. Ein `.ps1` selbst startet bei Doppelklick **nicht**
automatisch PowerShell (öffnet sich standardmäßig im Text-Editor), deshalb der Umweg über
eine echte `.lnk`-Verknüpfung:
```powershell
. .\TradingJournal-Weaver\create-desktop-shortcut.ps1
```

## 3. `.env` anlegen

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
| `MAX_GAP_DAYS` | Optional — Tage, die eine glattgestellte Kampagne *PENDING* bleibt, bevor sie *CLOSED* wird (Standard `10`, ganze Zahl ≥ 1) |
| `TRADE_XML_DIR` / `TRADE_CSV_DIR` | Optional — Ablageordner für die IBKR-Berichte (XML bzw. Kontoauszug-CSV). Standard: Windows `C:\Trade_XML` / `C:\Trade_CSV`, Linux/macOS `~/Trade_XML` / `~/Trade_CSV`. Alle Unterordner werden darunter angelegt |

**Sicherheit:** `.env` ist in `.gitignore` — niemals committen.

**`users.toml`** (lokal, gitignored — aus `users.toml.example` kopieren: `copy users.toml.example users.toml`) ist die zentrale, einzige Quelle
für die User↔Prefix-Zuordnung (`dein_user` → `dein_user_`, `zweiter_user` → `zweiter_user_`) — `DEFAULT_USER`
oben, `accounts.toml` (Kontozuordnung) und `pipeline.toml` (Schritt 5) lösen den Prefix alle von
dort auf. Jeder dort genannte User muss in `users.toml` stehen, sonst bricht der Import mit einer
Meldung ab. Ebenso anlegen: `accounts.toml` aus `accounts.toml.example` (Kontozuordnung, letzte vier
Ziffern der IBKR-Kontonummer → User + Environment).

Die `DB_NAME_*`-Variablen (`ibkr_money`, `ibkr_paper`, `ibkr_test`, `ibkr_autom_money`,
`ibkr_autom_paper`) müssen normalerweise nicht angepasst werden — sie legen die
tatsächlichen MySQL-Datenbanknamen fest und werden von TradingJournal (`config/database.php`)
in gleicher Form erwartet.

## 4. Datenbanken initialisieren

⚠️ **Destruktiv** — legt Datenbank + alle Tabellen aus `sql/` neu an, löscht bestehende Daten
des jeweiligen Environment/Prefix-Paars. Nur beim ersten Setup bzw. bewusstem Reset ausführen.

Für jede benötigte Kombination aus Environment × Nutzer-Prefix einmal ausführen — `test` immer
(Start-Environment der Weboberfläche, solange `TRADING_DEFAULT_ENV` nicht gesetzt ist):

```bash
python -m tools.maintenance.reset_IBKR_DB test dein_user_
python -m tools.maintenance.reset_IBKR_DB money dein_user_
python -m tools.maintenance.reset_IBKR_DB paper dein_user_
```

Zusätzliche Tabellen außerhalb des Kern-Schemas (z.B. Psychology-Modul) werden **nicht**
über `reset_IBKR_DB.py` angelegt, sondern über eigene Setup-Scripts in
`tools/maintenance/`, damit ein Reset nicht versehentlich fachfremde Tabellen mitlöscht:

```bash
python -m tools.maintenance.setup_psychology_tables money dein_user_
```

**Für einen zusätzlichen, weiteren User** (z.B. ein Familienmitglied, nachdem die
Grundinstallation schon steht): diesen Schritt mit dem neuen Prefix wiederholen (`users.toml`
ggf. vorher um den neuen User ergänzen, siehe Schritt 3), danach den passenden Laravel-User
anlegen (siehe TradingJournal-Setup-Anleitung, Schritt 5) — **mit demselben Prefix** auf
beiden Seiten.

## 5. `pipeline.toml` anlegen

```bash
copy pipeline.toml.example pipeline.toml
```

`pipeline.toml` ist **maschinenspezifisch** und daher wie `.env` in `.gitignore` (nicht
versioniert) — jede Maschine trägt hier nur die User/Environments ein, die auf **ihr**
tatsächlich per Schritt 4 initialisiert wurden. Ein Eintrag für einen User, dessen Tabellen
auf dieser Maschine nicht existieren, lässt `run_pipeline.py` im Auto-Modus mit
"Tabelle nicht gefunden" fehlschlagen.

```toml
[users.dein_user]
environments = ["money"]   # nur die Environments, die in Schritt 4 initialisiert wurden

[[test]]                   # TEST je User als eigener Block (steht schon in der Vorlage),
user = "dein_user"         # nicht zusätzlich in environments — sonst läuft TEST doppelt
```

Kein `prefix =` nötig — der wird automatisch aus `users.toml` aufgelöst (User-Name = Name
der Sektion, hier `dein_user`). Nur falls ein User (noch) nicht in `users.toml` steht, hier per
`prefix = "..."` explizit setzen.

## 6. Ersten Lauf testen

```bash
python run_pipeline.py --dry-run
```

Zeigt alle konfigurierten Steps/Befehle laut `pipeline.toml`, ohne etwas auszuführen.
Danach für einen echten Testlauf (User-/Env-Namen an die eigene `pipeline.toml` anpassen):

```bash
python run_pipeline.py --users dein_user --envs test
```

## 7. Altdaten nachholen (einmalig)

Die tägliche Query deckt nur die letzten n Tage ab. Historie vor der Installation einmalig im
Kundenportal abrufen: Flex Query **Starten**, Zeitraum *Benutzerdefinierter Zeitraum*, Format
XML (max. 365 Tage je Abruf, vom Portal erzwungen; Paper-Konten nur rund 180 Tage rückwirkend, frühere Tage sind im Kalender gesperrt). Die `.xml`-Dateien nach
`C:\Trade_XML\incoming_mail\` legen (Dateiname egal, Routing über `accountId` →
`accounts.toml`), dann regulär `python run_pipeline.py`.

**Vor dem ersten produktiven `process`-Lauf** einspielen bzw. im selben Lauf: `process` sortiert
nur die unverarbeiteten Zeilen (`trades_raw.processed=0`) nach `dateTime`. Alte Trades, die nach
bereits verarbeiteten neueren kommen, laufen danach durch das FIFO-Matching und verfälschen
Tranchen und Kampagnen. Überlappungen mit den täglichen Berichten fängt der Checksum-Dedup ab.
Kontostände (`account_snapshots`) kommen nur aus Kontoauszug-CSVs mit **einem** Stichtag
(`Statement,Data,Period`): rückwirkend nur per Einzel-Download je Tag im Portal (*Täglich* +
Datum → CSV) nach `C:\Trade_CSV\incoming\`, Routing über die `accountId` in der CSV,
Reihenfolge egal (Dedup je `snapshot_date`). Monats-/Zeitraumauszüge haben kein parsebares
Einzeldatum → *Kein Datum im CSV — übersprungen*, Datei bleibt in `incoming\` liegen.

## 8. Web-API: DNS-Auflösung des IBKR-Hosts

`get_flexquery_api.py` ruft `gdcdyn.interactivebrokers.com` auf. Der Name ist kein einfacher
A-Eintrag, sondern eine Akamai-CNAME-Kette:

```
gdcdyn.interactivebrokers.com
  → www.interactivebrokers.com.edgekey.net
    → e72360.a.akamaiedge.net → A-Records (wechselnd)
```

DNS-Forwarder in Handy-Hotspots (Android: `192.168.43.x`) und manchen kleinen Routern bzw. der
DNS des Mobilfunkanbieters dahinter scheitern an dieser Kette (`nslookup` → `Server failed`),
während kurze Namen weiter aufgelöst werden. Folge im Log: `NameResolutionError … [Errno 11002]
getaddrinfo failed`. Die Anfrage erreicht IBKR nicht — kein Token-/Query-Fehler und kein
fehlgeschlagener Versuch im Sinne der Sperre 1025. Der Mail-Abruf (`get_flexquery_emails.py`)
nutzt andere Hostnamen und ist nicht betroffen.

Behebung: feste DNS-Server (1.1.1.1, 8.8.8.8) auf dem Netzwerkadapter, Schritte in
[Fehlerbehebung und häufige Fragen](../benutzer/90-fehlerbehebung.md). Hintergrund dazu:

- Windows speichert die Einstellung **je Adapter** in der Registry
  (`HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\{Adapter-GUID}`):
  `NameServer` = feste Server, `DhcpNameServer` = Vorschlag des Routers/Hotspots. Ist
  `NameServer` gesetzt, hat er Vorrang.
- Sie gilt unabhängig vom verbundenen Netz und übersteht Netzwechsel, Neustart und
  Neustart des Hotspot-Handys. Sie gilt aber **nur für diesen Adapter** — WLAN, Ethernet und
  USB-Tethering haben jeweils eigene Einträge.
- Tritt der Fehler trotz Fix wieder auf, zuerst prüfen, ob die Einstellung noch gesetzt ist
  (PowerShell, ohne Administrator):

  ```powershell
  Get-DnsClientServerAddress -InterfaceAlias "WLAN" -AddressFamily IPv4
  ```

  Steht dort die Adresse des Routers/Hotspots statt `1.1.1.1, 8.8.8.8`, wurde sie zurückgesetzt
  (z. B. durch Netzwerk-Reset oder Windows-Update) und muss neu gesetzt werden.
- Offene WLANs mit Anmeldeseite (Hotel, Bahn) zeigen diese mit festen DNS-Servern teils nicht an.
  Dann vorübergehend `-ResetServerAddresses`, anmelden, danach wieder setzen.

---

## Weiterführende Dokumentation

| Datei | Inhalt |
|---|---|
| `docs/handbuch/technik/30-befehlsreferenz.md` | Vollständige Befehlsreferenz aller Scripts |
| `docs/handbuch/technik/10-architektur-und-pipeline.md` | Architektur, FIFO-Logik, DB-Schema im Detail |
| [Installation: TradingJournal](60-installation-tradingjournal.md) | Setup der Weboberfläche (liest dieselben Datenbanken) |
