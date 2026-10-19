# Installation: Windows-Grundausstattung

> Ausführlichere, für Einsteiger geschriebene Version mit mehr Erklärungen:
> [Benutzerhandbuch: Windows vorbereiten](../benutzer/30-windows-vorbereiten.md).

Diese Seite deckt die **Basis-Software** ab, die auf einem neuen Windows-Rechner installiert
sein muss, bevor die projektspezifischen Setup-Anleitungen ([Installation: TradingJournal-Weaver](50-installation-weaver.md),
[TradingJournal-Setup](60-installation-tradingjournal.md))
funktionieren. Beschreibt lokale Entwicklungsrechner.

---

## Übersicht

| Software | Wofür | Woher |
|---|---|---|
| Git for Windows | Repos klonen/verwalten | [git-scm.com/download/win](https://git-scm.com/download/win) |
| XAMPP | Apache, PHP, MySQL (lokale DB) | [apachefriends.org](https://www.apachefriends.org/) |
| Composer | PHP-Abhängigkeiten (TradingJournal) | [getcomposer.org](https://getcomposer.org/download/) |
| Node.js + npm | Frontend-Assets bauen (Vite) | [nodejs.org](https://nodejs.org/) (LTS) |
| Python 3.14 | Import-Pipeline (TradingJournal-Weaver) | [python.org](https://www.python.org/downloads/) |

("Artisan" ist **kein** eigenes Programm — siehe Hinweis am Ende.)

---

## 1. Git for Windows

- Installer ausführen, Option **"Git from the command line and also from 3rd-party software"**,
  restliche Defaults übernehmen.
- Prüfen: `git --version`
- Einmalig konfigurieren (PowerShell) — nur nötig, wenn eigene Commits gemacht werden; Klonen
  und Updates (`git pull`, `update.ps1`) brauchen es nicht:
  ```powershell
  git config --global user.name "<Name>"
  git config --global user.email "<Mail>"
  ```
- Prüfen, ob die Werte gesetzt sind:
  ```powershell
  git config --global --list
  ```
- **GitHub-Authentifizierung (HTTPS + Windows Credential Manager):** Der Git-for-Windows-
  Installer bringt den **Git Credential Manager** bereits mit (`credential.helper` ist
  danach automatisch auf `manager` gesetzt — mit `git config --global --list` prüfbar,
  Zeile `credential.helper=manager`). Beim ersten `git push`/`git pull` gegen ein GitHub-Repo
  öffnet sich ein Browser-Fenster zum GitHub-Login; die Zugangsdaten landen danach im Windows-
  Anmeldeinformationsspeicher und werden bei künftigen Aufrufen automatisch wiederverwendet —
  kein `gh`-CLI nötig (ist in diesem Projekt bewusst nicht installiert).

## 2. XAMPP (Apache + PHP + MySQL)

Dieses Projekt nutzt lokal den **kompletten XAMPP-Stack** — Apache, PHP und MySQL laufen
alle über das XAMPP-Control-Panel. Wie im restlichen Projekt üblich, ist hier durchgängig
von **MySQL** die Rede (auch wenn XAMPP technisch die MySQL-kompatible MariaDB bündelt —
für dieses Projekt ohne relevanten Unterschied, PyMySQL/PDO-MySQL sprechen dasselbe
Protokoll).

**Wichtig bei der Wahl der XAMPP-Version:** Apache Friends bietet mehrere parallele
Versionszweige an. `composer.json` von TradingJournal verlangt `php: ^8.2` (Laravel 12) —
also den **XAMPP-8.2.x-Zweig** (oder neuer) herunterladen, nicht die jeweils "neueste"
Version ungeprüft nehmen, falls die aktuellste einen anderen PHP-Major bündelt.

### Installation

1. Installer von [apachefriends.org](https://www.apachefriends.org/) laden, Standardpfad
   `C:\xampp` verwenden.
2. Bei der Komponentenauswahl mindestens **Apache**, **MySQL**, **PHP** aktiviert lassen —
   restliche Komponenten (FileZilla, Mercury, Tomcat) werden nicht gebraucht.
3. **XAMPP Control Panel** starten, **Apache** und **MySQL** über die jeweiligen "Start"-Buttons
   hochfahren. Für den Standardbetrieb mit `php artisan serve` reicht MySQL; Apache wird nur für
   den VirtualHost-Betrieb gebraucht ([Installation: TradingJournal](60-installation-tradingjournal.md),
   Variante B).
4. Prüfen: `php -v` (muss `PHP 8.2.x` oder höher zeigen), MySQL-Client testen mit
   `C:\xampp\mysql\bin\mysql -u root -p` (Standard-Passwort bei frischer XAMPP-Installation:
   leer).

### PHP zum PATH hinzufügen

XAMPP trägt sich **nicht automatisch** in die `PATH`-Umgebungsvariable ein — ohne diesen
Schritt funktionieren `php`, `php artisan` und `composer` nur, wenn man direkt im
XAMPP-Ordner steht.

**Über die Windows-Oberfläche:**
1. Windows-Taste drücken, "Umgebungsvariablen" eingeben → **"Umgebungsvariablen für dieses
   Konto bearbeiten"** öffnen.
2. Unter **"Benutzervariablen"** die Variable **`Path`** markieren → **Bearbeiten**.
3. **Neu** → `C:\xampp\php` eintragen → optional zweiten Eintrag `C:\xampp\mysql\bin`
   ergänzen (damit auch `mysql`/`mysqldump` direkt ohne vollen Pfad aufrufbar sind) → mit
   **OK** überall bestätigen.
4. **Alle offenen Terminals/IDEs schließen und neu öffnen** — PATH-Änderungen wirken erst
   in neu gestarteten Prozessen.

**Alternative per PowerShell** (kein Admin nötig, wirkt nur für den aktuellen Windows-Account):
```powershell
[Environment]::SetEnvironmentVariable(
    "Path",
    $env:Path + ";C:\xampp\php;C:\xampp\mysql\bin",
    "User"
)
```
Danach ebenfalls alle offenen Terminals neu starten. Prüfen mit `php -v` in einem **neuen**
Terminal-Fenster.

### PHP-Extension `zip` aktivieren

XAMPP liefert PHP standardmäßig mit der `zip`-Extension **deaktiviert** aus — Composer
(für `TradingJournal`) braucht sie aber, um Pakete zu entpacken. Ohne diesen Schritt bricht
`composer install` später mit einem Hinweis wie "`zip extension not found`" oder "`... zip
extension and unzip/7z commands are both missing`" ab bzw. warnt zumindest.

1. `C:\xampp\php\php.ini` in einem Text-Editor öffnen.
2. Zeile `;extension=zip` suchen (Suche nach `zip`) und das führende `;` entfernen, sodass
   dort `extension=zip` steht.
3. Datei speichern.
4. Neues Terminal öffnen (Ini-Änderungen wirken erst dort). Prüfen:
   ```powershell
   php -m | findstr -i zip
   ```
   sollte `zip` auflisten. Falls Apache bereits läuft, danach ebenfalls neu starten.

### XAMPP als Windows-Dienst installieren

Standardmäßig laufen Apache/MySQL nur, solange das XAMPP Control Panel offen ist und die
Module manuell gestartet wurden. Als Windows-Dienst installiert, starten sie automatisch
beim Systemstart und laufen unabhängig vom Control Panel weiter — praktisch, wenn man nicht
jedes Mal vor der Arbeit erst das Control Panel öffnen und beide Module anklicken will.

**Über das XAMPP Control Panel (einfachster Weg):**
1. XAMPP Control Panel **als Administrator** starten (Rechtsklick → "Als Administrator
   ausführen") — ohne Admin-Rechte lässt sich kein Dienst registrieren.
2. In der Zeile **Apache** die Checkbox ganz links in der Spalte **"Svc"** anklicken →
   registriert Apache als Windows-Dienst. Gleiches für die Zeile **MySQL**.
3. Beide Zeilen zeigen danach "Running" auch nach Neustart, ohne dass sie manuell erneut
   gestartet werden müssen. Kontrolle: `services.msc` öffnen → **Apache2.4** und **MySQL**
   sind gelistet, Starttyp auf **Automatisch** setzen (Rechtsklick → Eigenschaften), falls
   das nicht schon der Fall ist.

**Alternative per Kommandozeile** (falls die Checkbox-Methode nicht greift — PowerShell **als
Administrator**):
```powershell
C:\xampp\apache\bin\httpd.exe -k install -n "Apache2.4"
C:\xampp\mysql\bin\mysqld.exe --install MySQL --defaults-file="C:\xampp\mysql\bin\my.ini"

net start Apache2.4
net start MySQL
```
Rückgängig machen (Dienst entfernen, z.B. um zurück auf manuellen Start via Control Panel
zu wechseln):
```powershell
C:\xampp\apache\bin\httpd.exe -k uninstall -n "Apache2.4"
C:\xampp\mysql\bin\mysqld.exe --remove MySQL
```

**Datenbank-Zugangsdaten:** Frisches XAMPP hat den User `root` **ohne Passwort**. Für dieses
Projekt in `.env`/`TradingJournal-Weaver/.env` entsprechend `DB_PASS=`/`TRADING_DB_PASSWORD=` leer lassen,
oder — empfohlen — ein Passwort setzen (`ALTER USER 'root'@'localhost' IDENTIFIED BY '...'`)
und in beiden `.env`-Dateien eintragen.

**Port-Konflikte:** Apache belegt standardmäßig Port 80 — falls das fehlschlägt (Skype, IIS,
ein anderer Webserver), im XAMPP Control Panel unter "Config" → `httpd.conf` den Port ändern.
MySQL läuft auf dem für dieses Projekt erwarteten Standardport 3306, hier normalerweise keine
Anpassung nötig.

Ein Produktionsserver läuft üblicherweise mit einer **Standalone-MySQL-Installation** statt
XAMPP — ein bewusster, bekannter Unterschied zwischen lokaler Entwicklung und Produktion, hier
nicht weiter behandelt.

## 3. Composer

- Installer von [getcomposer.org](https://getcomposer.org/download/) (`Composer-Setup.exe`)
  ausführen — erkennt eine vorhandene PHP-Installation automatisch; falls nicht gefunden,
  manuell auf `C:\xampp\php\php.exe` zeigen.
- Prüfen: `composer -V`

## 4. Node.js + npm

- LTS-Installer von [nodejs.org](https://nodejs.org/) — Standardoptionen reichen.
- Prüfen: `node -v` und `npm -v`

## 5. Python 3.14

- Installer von [python.org](https://www.python.org/downloads/).
- **Wichtig:** Beim Installer die Checkbox **"Add python.exe to PATH"** aktivieren — sonst
  funktionieren `python`/`pip` nicht direkt im Terminal.
- Prüfen: `python --version` und `pip --version`

---

## 6. Projektverzeichnis anlegen und Repos klonen

PowerShell startet **nicht** automatisch im gewünschten Arbeitsverzeichnis — das
Startverzeichnis hängt davon ab, wie das Fenster geöffnet wurde:

| Wie geöffnet | Standard-Startverzeichnis |
|---|---|
| Normal übers Startmenü / Windows Terminal | meist `C:\Users\<Benutzername>` |
| **"Als Administrator ausführen"** (Rechtsklick) | `C:\Windows\System32` — häufigste Ursache für "ich lande immer in system32" |

`Set-Location` (Alias: `cd`) wechselt das Verzeichnis, `Get-Location` (Alias: `pwd`) zeigt,
wo man gerade steht. Root-Ordner fürs Projekt anlegen und hineinwechseln:

```powershell
New-Item -ItemType Directory -Force -Path C:\Users\<Benutzername>\trading
Set-Location C:\Users\<Benutzername>\trading
```

**`C:\Users\<Benutzername>\trading\` ist frei wählbar, keine technische Vorgabe** — es ist
nur ein Vorschlag für den Ordner, unter dem das Projekt lokal liegt. Jeder beliebige Ordner
funktioniert genauso, z.B. `D:\dev\trading` oder `C:\trading`. **Was tatsächlich zählt:**
`TradingJournal-Weaver` und `TradingJournal` müssen als **direkte Geschwisterordner** im
selben Elternverzeichnis liegen — `TradingJournal/update.ps1` erwartet den Weaver unter
`../TradingJournal-Weaver` (relativ zum eigenen Skript). Liegt einer der beiden woanders, bricht
das Update-Skript ab.

**Unabhängig davon fest verdrahtet:** `C:\Trade_XML\` und `C:\Trade_CSV\` (die
IBKR-Import-Ordner) stehen in `import_ibkr_trades.py`, `get_flexquery_emails.py` und
`get_flexquery_api.py` als absolute Pfade **direkt an der Wurzel von Laufwerk C:**,
unabhängig davon, wo das Projekt selbst liegt — nicht konfigurierbar, nicht verschiebbar,
ohne Codeänderung.

**Manuelles Anlegen ist aber nicht nötig** — beide Ordner samt kompletter Unterstruktur
(`incoming_mail\`, `incoming_api\`, `incoming\`, `<env>\<user>\processed\`,
`test\<user>\incoming\`, etc.) werden von den Scripts selbst per `mkdir(exist_ok=True)`
beim ersten Lauf automatisch erzeugt, falls sie fehlen. Einzige Voraussetzung: der Prozess
braucht Schreibrechte auf `C:\` — bei einem normalen Benutzerkonto ohne Sonderbeschränkungen
ist das im Regelfall automatisch der Fall.

### Repos klonen

Bei `TradingJournal-Weaver` per Voreinstellung nur die zum **Betreiben** nötigen Dateien holen, ohne
Test-Suite/Tiefendokumentation/persönliche Einmal-Skripte (per Git **Sparse-Checkout** —
kein Abweichen von "alles kommt aus Git", `git pull` für spätere Updates funktioniert
danach ganz normal weiter). `TradingJournal` ist bereits ohne
Zusatz-Ballast, dort reicht ein normaler `git clone`:

```powershell
# Im leeren Root-Ordner (siehe oben):
git clone --filter=blob:none --no-checkout https://github.com/mike-1140/TradingJournal-Weaver.git
cd TradingJournal-Weaver
git sparse-checkout init --cone
git sparse-checkout set sql src tools/maintenance docs
git checkout master
cd ..

git clone https://github.com/mike-1140/TradingJournal.git
```

Ergebnis:
```
<gewählter Root-Ordner>\
├── TradingJournal-Weaver\    (nur sql/, src/, tools/maintenance/, docs/ + Root-Dateien wie run_pipeline.py)
└── TradingJournal\
```

Danach weiter mit [Installation: TradingJournal-Weaver](50-installation-weaver.md) (ab Schritt 2 — Repo ist ja
bereits geklont) und der TradingJournal-Setup-Anleitung.

### Nur für Entwicklung: vollständiger `TradingJournal-Weaver`-Klon

Wer an `TradingJournal-Weaver` selbst mitentwickeln will, braucht zusätzlich die Test-Suite,
Tiefendokumentation und die persönlichen Einmal-Skripte aus `dev/` — dafür einfach ganz
normal klonen, ohne Sparse-Checkout, **statt** der obigen drei `TradingJournal-Weaver`-Zeilen:

```powershell
git clone https://github.com/mike-1140/TradingJournal-Weaver.git
```

---

## Zu "Artisan"

`artisan` ist **kein separat zu installierendes Programm**, sondern ein PHP-Skript
(`TradingJournal/artisan`), das mit jedem Laravel-Projekt mitkommt. Voraussetzung dafür sind
nur PHP (Schritt 2) und die per Composer installierten Abhängigkeiten (TradingJournal-Setup,
Schritt 1). Aufruf immer aus dem Projektordner:

```bash
cd TradingJournal
php artisan --version
```

---

## Verifikations-Checkliste

Nach Installation aller Programme, jeweils in einem neuen Terminal:

```powershell
git --version
php -v            # >= 8.2
composer -V
node -v
npm -v
python --version  # 3.14
```

Sowie XAMPP Control Panel: Apache und MySQL zeigen "Running" (grün), und Abschnitt 6 oben
(Repos geklont, Ordnerstruktur stimmt).

Danach weiter mit [Installation: TradingJournal-Weaver](50-installation-weaver.md) und der
[TradingJournal-Setup-Anleitung](60-installation-tradingjournal.md)
für die projektspezifische Einrichtung.
