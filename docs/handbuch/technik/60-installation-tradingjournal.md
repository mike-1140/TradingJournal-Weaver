# Installation: TradingJournal

> Ausführlichere, für Einsteiger geschriebene Version mit mehr Erklärungen:
> [Benutzerhandbuch: TradingJournal installieren](../benutzer/50-tradingjournal-installieren.md).

Installations- und Erstinitialisierungs-Anleitung für `TradingJournal` auf einem neuen Rechner.

**Voraussetzung:** [`xml_proj`](https://github.com/mike-1140/xml_proj) ist bereits eingerichtet
(siehe [xml_proj-Setup](50-installation-xml-proj.md))
— TradingJournal zeigt nur Daten an, das Trading-Datenbankschema wird ausschließlich über
`xml_proj` verwaltet.

**Grundlegende Software** (XAMPP für PHP/Apache/MariaDB, Composer, Node.js) muss vorher
installiert sein — siehe [Windows-Grundausstattung](40-installation-windows.md).
Diese Seite setzt das voraus und beschreibt nur noch die projektspezifische Einrichtung.

---

## Voraussetzungen

| Software             | Version                             | Hinweis                                     |
| --------------------- | ----------------------------------- | ------------------------------------------- |
| PHP                  | ^8.2 (Projekt läuft mit Laravel 12) | Aus XAMPP, siehe Windows-Grundausstattung   |
| Composer             | aktuell                             |                                             |
| Node.js + npm        | aktuell                             | Für Vite-Asset-Build                        |
| MySQL/MariaDB Server | via XAMPP                           | Dieselbe Instanz wie `xml_proj`, Port 3306  |

---

## 1. Repository klonen + Abhängigkeiten

`TradingJournal` hat ein eigenes Git-Repository. Falls schon per Windows-Grundausstattung
Abschnitt 6 geklont, diesen Schritt überspringen.

```bash
git clone https://github.com/mike-1140/TradingJournal.git
cd TradingJournal

composer install
npm install
```

**Falls `composer install` mit einem Hinweis auf die fehlende `zip`-Extension abbricht bzw. warnt** (z.B. "`zip extension not found`" oder "`... zip extension and unzip/7z commands are both missing`"): 

XAMPP liefert PHP standardmäßig mit der `zip`-Extension **deaktiviert** aus. 

Fix:

1. `C:\xampp\php\php.ini` in einem Text-Editor öffnen.
2. Zeile `;extension=zip` suchen (Suche nach `zip`) und das führende `;` entfernen, sodass dort `extension=zip` steht.
3. Datei speichern.
4. Neues Terminal öffnen (PATH-/Ini-Änderungen wirken erst dort) und `composer install` erneut ausführen. Falls Apache/`php artisan serve` bereits läuft, diese(s) danach auch neu starten.

Prüfen, ob die Extension aktiv ist: `php -m | findstr -i zip` sollte `zip` auflisten.

**Komfort-Skript für künftige Sitzungen:** `open.ps1` (im `TradingJournal`-Ordner) wechselt in dieses Verzeichnis — mit vorangestelltem Punkt aufrufen, damit es im aktuellen Fenster wirkt, nicht nur im Skript selbst:

```powershell
. .\TradingJournal\open.ps1
```

Falls dabei eine Fehlermeldung wie *"...kann nicht geladen werden, da die Ausführung von
Skripts auf diesem System deaktiviert ist"* kommt (Standardeinstellung auf vielen frischen
Windows-Rechnern): einmalig als Administrator
`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`, danach neues Terminal öffnen und den Befehl erneut ausführen.

**Desktop-Verknüpfung (optional, einmalig einrichten):** `create-desktop-shortcut.ps1` (ebenfalls im `TradingJournal`-Ordner) legt eine `.lnk`-Verknüpfung auf dem Desktop an, die per Doppelklick PowerShell direkt im `TradingJournal`-Ordner öffnet — danach z.B. sofort `php artisan serve` möglich. Genau wie bei `xml_proj` der Umweg über eine `.lnk`-Verknüpfung, weil ein `.ps1` bei Doppelklick nicht automatisch PowerShell startet:

```powershell
. .\TradingJournal\create-desktop-shortcut.ps1
```

## 2. `.env` anlegen

```bash
copy .env.example .env
php artisan key:generate
```

**Wichtig:** `.env.example` liefert als Laravel-Standardvorlage `DB_CONNECTION=sqlite` — für dieses Projekt zwingend auf MySQL umstellen. Ergänzen:

```env
DB_CONNECTION=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_DATABASE=ibkr_laravel
DB_USERNAME=<mysql-user>
DB_PASSWORD=<mysql-pass>

TRADING_DB_HOST=127.0.0.1
TRADING_DB_PORT=3306
TRADING_DB_USERNAME=<mysql-user>
TRADING_DB_PASSWORD=<mysql-pass>
```

`DB_*` steuert die Laravel-eigene Datenbank (`users`, `sessions`, `cache` — Name frei
wählbar, z.B. `ibkr_laravel`). `TRADING_DB_*` steuert Zugangsdaten für die fünf
Trading-Datenbanken. Deren **Namen selbst** (`ibkr_money`, `ibkr_paper`, `ibkr_test`,
`ibkr_autom_money`, `ibkr_autom_paper`) sind in `config/database.php` fest hinterlegt und nicht über `.env` konfigurierbar — sie müssen mit den in `xml_proj/.env` (`DB_NAME_*`) definierten Namen übereinstimmen.

## 3. Laravel-eigene Tabellen anlegen

```bash
php artisan migrate
```

Legt `users` (inkl. `table_prefix`, `filter_preset`/`filter_from`/`filter_to`,
`dashboard_config`), `cache`, `sessions` an. **Nicht vergessen** — ohne diesen Schritt
existiert keine `users`-Tabelle und kein Login ist möglich.

## 4. Trading-Tabellen bereitstellen

Kein Laravel-Migrationsschritt. Falls noch nicht geschehen, in `xml_proj` ausführen
(siehe [xml_proj-Setup](50-installation-xml-proj.md) Schritt 5):

```bash
cd ../xml_proj
python -m tools.maintenance.reset_IBKR_DB money dein_user_
```

Prefix (`dein_user_` etc.) muss zu dem Prefix passen, der beim Anlegen des Users in Schritt 5
verwendet wird.

## 5. Ersten User anlegen

**Vorschritt, einmalig:** Die Spalte `is_admin` in der `users`-Tabelle hat **keine**
Laravel-Migration — sie wird nur durch diesen separaten Befehl per `ALTER TABLE` angelegt (idempotent, kann gefahrlos mehrfach laufen). Ohne diesen Schritt bricht
`auth:create-user --admin` mit `SQL: Column not found: is_admin` ab:

```bash
php artisan setup:auth
```

("`User ID 1 nicht gefunden`" ist an dieser Stelle normal, wenn noch kein User existiert — wichtig ist nur, dass die Spalte danach da ist.)

```bash
php artisan auth:create-user "Dein Name" dein_name@example.com "PASSWORT" --prefix=dein_user_ --admin
```

| Option                      | Bedeutung                                                            |
| --------------------------- | -------------------------------------------------------------------- |
| `name`, `email`, `password` | Pflichtargumente                                                     |
| `--prefix=`                 | Tabellen-Prefix, muss zum in Schritt 4 initialisierten Prefix passen |
| `--admin`                   | Setzt `is_admin=1`                                                   |

Der Befehl gibt nach dem Anlegen den passenden `reset_IBKR_DB`-Aufruf für den gewählten Prefix aus, falls Schritt 4 noch nicht erledigt wurde.

**Für einen zusätzlichen, weiteren User** (z.B. ein Familienmitglied, nachdem die
Grundinstallation schon steht): Schritt 4 (`xml_proj`-Tabellen) mit dem neuen Prefix
wiederholen, danach diesen Schritt hier noch einmal mit den neuen Zugangsdaten und
**demselben Prefix** ausführen.

## 6. Assets bauen

```bash
npm run build      # Produktion
# oder für Entwicklung mit Hot Reload:
npm run dev
```

## 7. Starten

Zwei Möglichkeiten — beide führen zur selben App, unterschiedlich bequem für den Alltag:

### Variante A: `php artisan serve` (einfach, aber manuell)

```bash
php artisan serve
```

`http://localhost:8000` aufrufen und mit den in Schritt 5 angelegten Zugangsdaten einloggen.
**Nachteil:** läuft nur, solange dieses Terminal-Fenster offen bleibt — bei jedem Neustart
erneut manuell ausführen.

### Variante B: Apache-VirtualHost (dauerhaft, kein manueller Start nötig)

Voraussetzung: XAMPPs Apache läuft (idealerweise als Windows-Dienst, siehe
[Windows-Grundausstattung](40-installation-windows.md)).
Dann liefert Apache die Seite automatisch mit Windows — kein `php artisan serve` mehr nötig. 

Zwei Teile:

**1. Windows-hosts-Datei** — ordnet den Namen (hier z.B. `trading.local`) der eigenen
Maschine zu, sonst findet der Browser den Namen gar nicht:

```powershell
# Pruefen, ob der Eintrag schon da ist:
Get-Content C:\Windows\System32\drivers\etc\hosts | Select-String "trading.local"

# Falls kein Ergebnis: als Administrator (PowerShell "Als Administrator ausfuehren") ergaenzen:
Add-Content -Path C:\Windows\System32\drivers\etc\hosts -Value "127.0.0.1 trading.local"
```

**2. Apache-VirtualHost** — `C:\xampp\apache\conf\httpd.conf` (oder
`C:\xampp\apache\conf\extra\httpd-vhosts.conf`, falls dort schon andere VHosts stehen)
öffnen und ergänzen (Pfad an den eigenen Root-Ordner anpassen):

```apache
<VirtualHost *:80>
    ServerName trading.local
    DocumentRoot "C:/Users/<Benutzername>/trading/TradingJournal/public"

    <Directory "C:/Users/<Benutzername>/trading/TradingJournal/public">
        Options -Indexes +FollowSymLinks
        AllowOverride All
        Require all granted
    </Directory>
</VirtualHost>
```

Falls in `httpd.conf` bei `NameVirtualHost`/mehreren VHosts noch keine Grundkonfiguration für Port 80 existiert, reicht in der Regel der obige Block allein (XAMPPs Standard-`Listen 80` bleibt bestehen).

Danach Apache im XAMPP Control Panel neu starten (Stop → Start), und `http://trading.local` im Browser aufrufen.

**Troubleshooting:** Falls `http://trading.local` nicht erreichbar ist — zuerst den
hosts-Eintrag prüfen (Befehl oben), dann `C:\xampp\apache\logs\error.log` auf
Konfigurationsfehler prüfen, danach `C:\xampp\apache\bin\httpd.exe -t` (testet die
`httpd.conf`-Syntax, ohne zu starten).

---

## Weiterführende Dokumentation

| Datei                                                | Inhalt                                                                   |
| ---------------------------------------------------- | ------------------------------------------------------------------------ |
| `CLAUDE.md`                                          | Entwickler-Notizen, Architektur-Patterns (Environment/Zeitfilter-Traits) |
| [xml_proj-Setup](50-installation-xml-proj.md) | Setup der Datenimport-Pipeline (Python) |
