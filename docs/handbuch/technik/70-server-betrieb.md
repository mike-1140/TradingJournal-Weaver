# Server-Betrieb — TradingJournal auf einem eigenen Server

Alternative zur lokalen Installation (siehe [Installation: TradingJournal](60-installation-tradingjournal.md)):
TradingJournal + TradingJournal-Weaver laufen auf einem eigenen Windows Server (physisch, VPS, oder ein
Rechner, der dauerhaft eingeschaltet bleibt) statt auf dem lokalen Arbeitsplatz-PC. Sinnvoll,
wenn du von mehreren Geräten (Laptop, Reise-Notebook, Tablet) auf dasselbe Journal zugreifen
willst, ohne die Datenbank mehrfach zu pflegen.

**Diese Anleitung ersetzt nicht** [Installation: TradingJournal-Weaver](50-installation-weaver.md)/
[Installation: TradingJournal](60-installation-tradingjournal.md) — sie überträgt dieselben Konzepte auf
einen Server-Kontext. Grundkenntnisse aus diesen beiden Dokumenten werden vorausgesetzt.

## Voraussetzungen

- Ein Windows-Server oder dauerhaft laufender Windows-Rechner, erreichbar per Remote-Zugriff
  (RDP, ein Remote-Desktop-Tool deiner Wahl, oder physischer Zugriff)
- **Ein eigenes VPN oder ein Reverse-Proxy mit Authentifizierung**, um den Server sicher von
  außen erreichbar zu machen — diese Anleitung geht davon aus, dass du diesen Teil bereits
  gelöst hast. Ein einfacher, kostenloser Einstieg: [Tailscale](https://tailscale.com/) (baut
  ein privates Mesh-VPN zwischen deinen Geräten auf, jedes Gerät bekommt eine feste,
  ausschließlich innerhalb des VPNs erreichbare IP-Adresse). Andere Optionen: WireGuard,
  klassisches Site-to-Site-VPN, oder ein Reverse-Proxy mit eigener Auth-Schicht.

**Wichtig — niemals ungeschützt am offenen Internet betreiben:** Diese Anleitung bindet
Apache bewusst nur an die private VPN-Adresse des Servers, nicht an die öffentliche IP
(siehe Firewall-Abschnitt unten). TradingJournal hat kein eigenes Rate-Limiting/Brute-Force-
Schutz für den Login und ist nicht für einen öffentlich erreichbaren Betrieb konzipiert.

---

## Notation in dieser Anleitung

Jeder Befehlsblock ist mit einem Label gekennzeichnet, welches Fenster/Programm gemeint ist:

- **[PowerShell]** — normales PowerShell-Fenster
- **[PowerShell – Administrator]** — PowerShell-Icon rechtsklicken → "Als Administrator
  ausführen" (nötig für Service-Steuerung, Firewall-Regeln, Schreibrechte-Änderungen)
- **[MySQL-Client]** — am `mysql>`-Prompt (siehe Schritt 2)
- **[Text-Editor]** — eine Datei mit einem Texteditor bearbeiten (Editor/Notepad reicht)
- **[Installer-GUI]** — Klicks innerhalb eines grafischen Installations-Assistenten
- **[Windows-Einstellungen]** — Systemsteuerung/Einstellungen-App, kein Terminal

Platzhalter: `<server-vpn-ip>` (die private VPN-Adresse des Servers), `<db-passwort>`
(selbst gewähltes, sicheres Passwort für den App-Datenbank-User).

---

## Schritt 1 — Git for Windows

Download: https://git-scm.com/install/windows („Click here to download“)

- [ ] **[Installer-GUI]** Installieren mit Option **"Git from the command line and also
  from 3rd-party software"**, sonst Defaults
- [ ] **[PowerShell]** Prüfen: `git --version`

---

## Schritt 2 — MySQL 8.4 LTS

Download: https://dev.mysql.com/downloads/installer/

- [ ] **[Installer-GUI]** Setup Type: **Custom** → **MySQL Server 8.4.x** auswählen — die
  Versionsnummer beim Auswählen genau prüfen, der Installer listet oft mehrere Versionen
  gleichzeitig auf. Ältere Versionen (z. B. 8.0) haben ihren offiziellen Support-Zeitraum
  bereits beendet und sollten für einen Server mit echten Finanzdaten nicht verwendet werden.
- [ ] **[Installer-GUI]** Config Type: **Server Computer**, Port **3306**
- [ ] **[Installer-GUI]** Root-Passwort setzen und sicher notieren
- [ ] **[Installer-GUI]** Windows Service Name: `MySQL84`, Autostart: **Ja**

### Passwort vergessen/zurücksetzen

Falls das Root-Passwort verloren geht: der MySQL Installer (Reconfigure → "Accounts and
Roles") verlangt dafür das *aktuelle* Passwort und hilft bei einem vergessenen Passwort
nicht. Stattdessen über eine **Init-Datei** (der Server führt sie beim Start einmalig aus,
ganz ohne bestehendes Passwort):

1. **[PowerShell – Administrator]** Service stoppen: `net stop MySQL84`
2. **[Text-Editor]** Init-Datei anlegen (Notepad: Zeile eintippen, Speichern unter
   `C:\mysql-init.txt`, Dateityp "Alle Dateien", Kodierung **ANSI**):
   ```
   ALTER USER 'root'@'localhost' IDENTIFIED BY 'NeuesSicheresPasswort123!';
   ```
3. **[PowerShell – Administrator]** MySQL manuell im Vordergrund starten, mit Verweis auf
   die echte `my.ini` (ohne `--defaults-file` sucht `mysqld` das Datenverzeichnis am
   falschen Ort — Fehler `Failed to set datadir ... No such file or directory`). Dieses
   Fenster offen lassen:
   ```powershell
   & "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqld.exe" --defaults-file="C:\ProgramData\MySQL\MySQL Server 8.4\my.ini" --init-file=C:\mysql-init.txt --console
   ```
   Warten, bis `ready for connections` im Log erscheint.
4. **[PowerShell]** — ein neues, zweites Fenster öffnen, Login testen:
   ```powershell
   & "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe" -u root -p
   ```
5. Zurück zum ersten Fenster, dort `Strg+C` zum Stoppen.
6. **[PowerShell – Administrator]** Init-Datei löschen (enthält Passwort im Klartext):
   `Remove-Item C:\mysql-init.txt`, dann Service normal starten: `net start MySQL84`

### Datenbanken + App-User anlegen — [MySQL-Client]

Verbinden entweder über die Startmenü-Verknüpfung "MySQL 8.4 Command Line Client", oder aus
**[PowerShell]** heraus mit `& "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe" -u root -p`
(der Prompt wechselt dann im selben Fenster von `PS C:\...>` zu `mysql>`).

```sql
CREATE DATABASE ibkr_laravel     CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE ibkr_money       CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE ibkr_paper       CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE ibkr_autom_money CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE ibkr_autom_paper CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER 'trading_app'@'%' IDENTIFIED BY '<db-passwort>';
GRANT ALL PRIVILEGES ON ibkr_laravel.*     TO 'trading_app'@'%';
GRANT ALL PRIVILEGES ON ibkr_money.*       TO 'trading_app'@'%';
GRANT ALL PRIVILEGES ON ibkr_paper.*       TO 'trading_app'@'%';
GRANT ALL PRIVILEGES ON ibkr_autom_money.* TO 'trading_app'@'%';
GRANT ALL PRIVILEGES ON ibkr_autom_paper.* TO 'trading_app'@'%';
FLUSH PRIVILEGES;
```

Nur die Environments anlegen, die du tatsächlich brauchst — `ibkr_test` kann entfallen,
wenn kein Test-Environment genutzt wird. Die App startet dann im Environment aus
`TRADING_DEFAULT_ENV` bzw. automatisch im ersten Environment mit Tabellen (siehe Schritt 8).

**Host bewusst `%` statt `127.0.0.1`:** MySQL löst eine eingehende Verbindung von
`127.0.0.1` serverseitig per Reverse-Lookup standardmäßig zu `localhost` auf und matcht die
Rechte-Tabelle gegen den aufgelösten Namen, nicht die rohe IP. Ein User mit der exakten IP
`127.0.0.1` als Host matcht dann nie und liefert `Access denied for user '...'@'localhost'`
— auch mit explizitem `-h 127.0.0.1` am Client, da das Problem serverseitig sitzt. `%`
umgeht dieses Hostname-Auflösungs-Problem komplett. Sicherheitsmäßig unkritisch, solange
`bind-address` (nächster Schritt) auf `127.0.0.1` steht — von außen kommt dann ohnehin nie
eine TCP-Verbindung an, unabhängig vom User-Host-Feld.

**MySQL nur lokal lauschen lassen — [Text-Editor] + [PowerShell – Administrator]:**

`exit` im MySQL-Client, dann `C:\ProgramData\MySQL\MySQL Server 8.4\my.ini` öffnen:
```ini
[mysqld]
bind-address = 127.0.0.1
```
Speichern, dann `net stop MySQL84 && net start MySQL84`.

**Verifizieren** (kein phpMyAdmin nötig — reicht der MySQL-Client selbst):
```sql
SHOW DATABASES;
SELECT User, Host FROM mysql.user WHERE User = 'trading_app';
SHOW VARIABLES LIKE 'bind_address';   -- erwartet: 127.0.0.1
```

---

## Schritt 3 — Python 3.14

Download: https://www.python.org/downloads/

- [ ] **[Installer-GUI]** **"Add python.exe to PATH"** + **"Install for all users"** aktivieren
- [ ] **[PowerShell]** — neues Fenster, prüfen: `python --version`, `pip --version`

---

## Schritt 4 — PHP 8.3 (Thread-Safe)

Download: https://windows.php.net/download/ → **PHP 8.3.x VS16 x64 Thread Safe** (ZIP)

- [ ] ZIP-Inhalt nach `C:\php` entpacken
- [ ] **[PowerShell]** `copy C:\php\php.ini-production C:\php\php.ini`
- [ ] **[Text-Editor]** `C:\php\php.ini` anpassen:
  ```ini
  extension_dir = "C:/php/ext"
  extension=curl
  extension=fileinfo
  extension=mbstring
  extension=openssl
  extension=pdo_mysql
  extension=zip
  extension=gd
  upload_max_filesize = 64M
  post_max_size = 64M
  max_execution_time = 120
  memory_limit = 256M
  ```
- [ ] **[Windows-Einstellungen]** `C:\php` zu System-PATH hinzufügen: Windows-Suche →
  "Umgebungsvariablen bearbeiten" → **Systemvariablen** → `Path` → **Bearbeiten** → **Neu**
  → `C:\php` eintragen
- [ ] **[PowerShell]** — neues Fenster, prüfen: `php --version`,
  `php -m | findstr -i "pdo_mysql mbstring"`

---

## Schritt 5 — Apache HTTP Server

Voraussetzung: Visual C++ Redistributable 2015-2022 x64 (falls noch nicht vorhanden, bei
Microsoft herunterladen und installieren).

Download: https://www.apachelounge.com/download/ (aktueller Build, z. B.
`httpd-2.4.x-win64-VS18.zip`). Die VC-Runtime ist rückwärtskompatibel zu PHPs VS16-Build,
das passt problemlos zusammen.

- [ ] ZIP-Inhalt nach `C:\Apache24` entpacken
- [ ] **[Text-Editor]** `C:\Apache24\conf\httpd.conf` ergänzen (an den passenden Stellen,
  nicht die ganze Datei ersetzen):

```apache
LoadModule php_module "C:/php/php8apache2_4.dll"
AddHandler application/x-httpd-php .php
PHPIniDir "C:/php"

LoadModule rewrite_module modules/mod_rewrite.so

DirectoryIndex index.php index.html

Listen <server-vpn-ip>:80

<VirtualHost <server-vpn-ip>:80>
    DocumentRoot "C:/trading/TradingJournal/public"
    ServerName trading

    <Directory "C:/trading/TradingJournal/public">
        Options -Indexes +FollowSymLinks
        AllowOverride All
        Require all granted
    </Directory>

    ErrorLog "C:/Apache24/logs/trading-error.log"
    CustomLog "C:/Apache24/logs/trading-access.log" combined
</VirtualHost>
```

**Wichtig:** `<server-vpn-ip>` durch die tatsächliche VPN-Adresse des Servers ersetzen
(zweimal — bei `Listen` und `<VirtualHost>`), sonst lauscht Apache auf eine nicht
existierende Adresse.

**[PowerShell – Administrator]**:
```powershell
C:\Apache24\bin\httpd.exe -k install -n "Apache2.4"
net start Apache2.4
```

**Firewall — nur das VPN-Netz erlauben** (Beispiel für Tailscales Standard-Adressbereich
`100.64.0.0/10`, bei anderem VPN entsprechend anpassen) — **[PowerShell – Administrator]**:
```powershell
New-NetFirewallRule -DisplayName "Trading HTTP (VPN only)" `
  -Direction Inbound -LocalPort 80 -Protocol TCP `
  -RemoteAddress 100.64.0.0/10 -Action Allow
```

**Keine zusätzliche "Block"-Regel anlegen:** Eine `Action Block`-Regel ohne eigene
`-RemoteAddress`-Einschränkung würde *alle* Adressen auf Port 80 blocken, einschließlich
des oben erlaubten VPN-Bereichs — Windows Firewall lässt eine passende Block-Regel immer
gegen eine passende Allow-Regel gewinnen, unabhängig von der Reihenfolge. Unnötig ohnehin:
Windows Firewall blockt standardmäßig bereits alles, was nicht explizit erlaubt ist.

- [ ] Apache-Service läuft, Autostart
- [ ] Test: Browser über die VPN-Adresse erreichbar; über die öffentliche IP des Servers
  **nicht** erreichbar (mit einem Gerät außerhalb des VPNs testen)

---

## Schritt 6 — Composer

Download: https://getcomposer.org/Composer-Setup.exe — PHP-Pfad `C:\php\php.exe` wird
automatisch erkannt. **[PowerShell]** prüfen: `composer --version`

---

## Schritt 7 — Code deployen

**[PowerShell]:**
```powershell
mkdir C:\trading
cd C:\trading

git clone https://github.com/mike-1140/TradingJournal-Weaver.git
git clone https://github.com/mike-1140/TradingJournal.git

mkdir C:\Trade_XML
mkdir C:\Trade_CSV
mkdir C:\Trade_XML\incoming_mail

cd C:\trading\TradingJournal-Weaver
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
deactivate
```

---

## Schritt 8 — `.env`-Dateien

**`C:\trading\TradingJournal-Weaver\.env`** — Vorlage `.env.example` kopieren und anpassen:
```ini
DB_USER=trading_app
DB_PASS=<db-passwort>
DB_HOST=127.0.0.1
DB_PORT=3306

DB_NAME_MONEY=ibkr_money
DB_NAME_PAPER=ibkr_paper
DB_NAME_AUTOM_MONEY=ibkr_autom_money
DB_NAME_AUTOM_PAPER=ibkr_autom_paper
```
Falls der Datenabruf (`get_flexquery_emails.py`/`get_flexquery_api.py`) weiterhin auf einem
anderen Gerät läuft und nur die fertigen Dateien auf diesen Server übertragen werden (siehe
[Verteilter Abruf — minimaler Client für den Datenabruf](80-verteilter-abruf.md)), bleiben `IMAP_*`/`IBKR_FLEX_QUERIES` hier leer.

**`C:\trading\TradingJournal\.env`** — Vorlage `.env.example` kopieren und anpassen:
```ini
APP_NAME="Trading Journal"
APP_ENV=production
APP_DEBUG=false
APP_URL=http://<server-vpn-ip>

DB_CONNECTION=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_DATABASE=ibkr_laravel
DB_USERNAME=trading_app
DB_PASSWORD=<db-passwort>

TRADING_DB_HOST=127.0.0.1
TRADING_DB_PORT=3306
TRADING_DB_USERNAME=trading_app
TRADING_DB_PASSWORD=<db-passwort>

TRADING_DEFAULT_ENV=MONEY
```

**`TRADING_DEFAULT_ENV`** legt fest, in welchem Environment die App nach dem Login startet
(ohne die Zeile: `TEST`). Auf dem Server ist `MONEY` meist die bessere Wahl. Hat der Benutzer im
eingestellten Environment keine Tabellen — etwa weil `ibkr_test` gar nicht angelegt wurde —,
startet die App automatisch im ersten Environment, in dem er welche hat
(`TradingHelper::getStartEnvironment()`, Reihenfolge wie in `config/trading.php`).

**`APP_KEY` wird im nächsten Schritt generiert, nicht manuell eintragen.**

---

## Schritt 9 — Laravel-Grundgerüst

**[PowerShell – Administrator]** (die `icacls`-Befehle brauchen Admin-Rechte):
```powershell
cd C:\trading\TradingJournal
composer install --no-dev --optimize-autoloader
php artisan key:generate

icacls "C:\trading\TradingJournal\storage" /grant "SYSTEM:(OI)(CI)F" /T
icacls "C:\trading\TradingJournal\bootstrap\cache" /grant "SYSTEM:(OI)(CI)F" /T
```

### Frontend-Build (Node.js/npm) — sonst "Vite manifest not found"

TradingJournal nutzt Vite (`@vite`-Direktiven in den Blade-Views) für kompiliertes CSS/JS —
ohne Build fehlt `public/build/manifest.json` und **jede** Seite mit `@vite` (inkl. Login)
liefert einen 500er.

1. Download: https://nodejs.org/ (aktuelle LTS-Version, Windows Installer), Standardoptionen.
2. **[PowerShell]** — neues Fenster, prüfen: `node --version`, `npm --version`
3. **[PowerShell]:**
   ```powershell
   cd C:\trading\TradingJournal
   npm install
   npm run build
   ```
   Erzeugt `public\build\manifest.json` + die kompilierten Assets.

---

## Schritt 10 — Datenbank einrichten

**Option A — frisches, leeres Journal:**
```powershell
cd C:\trading\TradingJournal-Weaver
.venv\Scripts\activate
python -m tools.maintenance.reset_IBKR_DB money dein_user_
# pro benötigtem Environment wiederholen (paper/autom_money/autom_paper)
deactivate

cd C:\trading\TradingJournal
php artisan migrate --force
php artisan setup:auth
php artisan auth:create-user "Dein Name" dein_name@example.com "PASSWORT" --prefix=dein_user_ --admin
```

**Option B — bestehende Daten von einem lokalen Rechner übernehmen:**

Auf dem **lokalen Rechner** (nicht auf dem Server), frische Dumps erzeugen — `mysqldump`s
eigenes `--result-file`-Flag nutzen, **nicht** PowerShells `>`-Redirection: Windows
PowerShell 5.1s `>` (= `Out-File` ohne `-Encoding`) schreibt standardmäßig UTF-16, was die
Textausgabe mit Null-Bytes zwischen jedem Zeichen zerschießt (`mysql` meldet beim Restore
dann `ASCII '\0' appeared in the statement`):
```powershell
& "<pfad-zu-mysqldump>" -u root --result-file=ibkr_laravel.sql ibkr_laravel
& "<pfad-zu-mysqldump>" -u root --result-file=ibkr_money.sql ibkr_money
# ... für jede weitere Environment-DB
```
Dumps zum Server übertragen (z. B. über dein Remote-Desktop-Tool, nicht über die
Zwischenablage — für größere Dateien unzuverlässig). Auf dem **Server** einspielen — auch
hier: PowerShell kennt den `<`-Umleitungsoperator nicht (`RedirectionNotSupported`),
deshalb über `cmd /c` mit einfachen Anführungszeichen außen:
```powershell
cmd /c '"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe" -h 127.0.0.1 -u trading_app -p ibkr_laravel < ibkr_laravel.sql'
cmd /c '"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe" -h 127.0.0.1 -u trading_app -p ibkr_money < ibkr_money.sql'
# ... für jede weitere Environment-DB
```
Damit sind Schema, Daten und echte Logins (`ibkr_laravel.users`) in einem Schritt
übernommen — keine separate `auth:create-user`/Schema-Anlage nötig. Danach trotzdem als
Sicherheitsnetz (überspringt bereits gelaufene Migrationen):
```powershell
cd C:\trading\TradingJournal
php artisan migrate --force
php artisan config:cache
php artisan route:cache
php artisan view:cache
net stop Apache2.4 && net start Apache2.4
```

- [ ] Login-Seite erscheint unter `http://<server-vpn-ip>/login`
- [ ] Login funktioniert

---

## Schritt 11 — `pipeline.toml` + `accounts.toml`

**[PowerShell]:**
```powershell
cd C:\trading\TradingJournal-Weaver
copy pipeline.toml.example pipeline.toml
```

**Wichtig — mitkopierten `[[test]]`-Block entfernen:** `pipeline.toml.example` liefert
standardmäßig einen aktiven (nicht auskommentierten) Block:
```toml
[[test]]
user = "dein_user"
```
Ein `[[test]]`-Eintrag ist laut `src/config.py::load_active_targets()` immer aktiv — kein
Enabled-Schalter, zum Deaktivieren muss der Eintrag komplett aus der Datei entfernt werden.
Bleibt er stehen und existiert keine `ibkr_test`-Datenbank, bricht die Pipeline mit
`Access denied ... to database 'ibkr_test'` ab.

Eigene User/Environments eintragen:
```toml
[settings]
steps = ["import", "process", "summary"]

[users.dein_user]
environments = ["money", "paper"]
```
(`fetch_emails`/`fetch_api`/`snapshot_csv` nur ergänzen, falls der Datenabruf auch auf
diesem Server laufen soll — sonst reichen `import`/`process`/`summary`, wenn die Rohdaten
von woanders hierher übertragen werden, siehe [Verteilter Abruf — minimaler Client für den Datenabruf](80-verteilter-abruf.md).)

**Zusätzlich nötig: `accounts.toml`** — das accountId→User/Environment-Mapping
(`src/config.py::load_account_map()`), eine eigene, gitignored Konfigurationsdatei neben
`.env` und `pipeline.toml`. Ohne sie meldet der Import "Unbekannte accountId ...
übersprungen" für jede Datei, nichts wird importiert. Vorlage `accounts.toml.example`
kopieren und mit den eigenen IBKR-accountId-Suffixen befüllen (siehe Kommentare in der
Vorlage).

---

## Schritt 12 — Abschlusstest

- [ ] `services.msc`: `MySQL84`/`Apache2.4` → Gestartet, Autostart
- [ ] Browser über die VPN-Adresse: `http://<server-vpn-ip>/login` erreichbar
- [ ] Login funktioniert, zeigt die erwarteten Daten
- [ ] Von einem Gerät **ohne** VPN-Verbindung: Server über seine öffentliche IP → keine
  Verbindung (Firewall greift)
- [ ] Ein Journal-Eintrag über die UI anlegen → wird korrekt gespeichert

---

## Troubleshooting

| Problem | Ursache | Lösung |
|---|---|---|
| MySQL-Client-Fenster (Startmenü-Verknüpfung) schließt sich sofort nach Passwort-Eingabe, keine Fehlermeldung | Falsches Passwort — die Verknüpfung schließt bei Fehler kommentarlos | Stattdessen über PowerShell verbinden (`& "...\mysql.exe" -u root -p`), Fehlermeldung bleibt dort stehen |
| `Access denied for user 'root'@'localhost'` trotz korrektem Passwort in einer Remote-Sitzung | Tastaturlayout-Mismatch zwischen lokalem Gerät und Server (Sonderzeichen im Passwort werden anders übertragen) | Tastaturlayout abgleichen, oder Passwort ohne Sonderzeichen setzen |
| `mysqld --init-file=...` bricht ab mit `Failed to set datadir ... No such file or directory` | `mysqld.exe` ohne `--defaults-file` gestartet, sucht Datenverzeichnis relativ zum `bin`-Ordner statt in `C:\ProgramData\MySQL\...` | `--defaults-file="C:\ProgramData\MySQL\MySQL Server 8.4\my.ini"` mit angeben |
| `Access denied for user 'trading_app'@'localhost'` trotz `-h 127.0.0.1` am Client | User wurde mit Host `127.0.0.1` statt `%` angelegt — MySQL löst die Verbindung serverseitig zu `localhost` auf | User mit Host `%` neu anlegen (siehe Schritt 2) |
| `mysqldump`-Restore scheitert mit `ASCII '\0' appeared in the statement` | Dump wurde über PowerShells `>`-Operator erzeugt (schreibt UTF-16 statt UTF-8) | Dump neu erzeugen mit `--result-file=` statt `>` |
| PowerShell meldet `Unerwartetes Token` bei `"pfad\programm.exe" -argument` | Ein in Anführungszeichen gesetzter Pfad wird ohne Call-Operator nur als String interpretiert | `&` vor den Pfad setzen: `& "pfad\programm.exe" -argument` |
| PowerShell meldet `Der Operator "<" ist für zukünftige Versionen reserviert` | PowerShell kennt keine `<`-Umleitung (im Gegensatz zu cmd/bash) | Über `cmd /c '"pfad\programm.exe" ... < datei'` ausführen (einfache Anführungszeichen außen) |
| Seite liefert 500 mit "Vite manifest not found" | Kein Frontend-Build durchgeführt | `npm install && npm run build` im TradingJournal-Ordner |
| "Diese Seite funktioniert nicht — zu oft weitergeleitet" nach Login | Meist eine fehlgeschlagene DB-Verbindung, die `bootstrap/app.php`s Exception-Handler abfängt und zu einem Redirect-Loop mit `/login` führt | Laravel-Log prüfen (`storage/logs/laravel.log`, nach `\]\s+\w+\.ERROR:` filtern) — üblicher Auslöser: `TRADING_DB_USERNAME`/`_PASSWORD` falsch/fehlend, oder der Benutzer hat in keinem Environment Tabellen (Prefix in der `users`-Tabelle prüfen, `reset_IBKR_DB.py` für diesen Prefix gelaufen?) |
| `run_pipeline.py` meldet "Unbekannte accountId ... übersprungen" für jede Datei | `accounts.toml` fehlt oder ist unvollständig | Siehe Schritt 11 |
| `run_pipeline.py` verarbeitet unerwartet auch ein TEST-Environment | Der mitkopierte `[[test]]`-Block aus `pipeline.toml.example` wurde nicht entfernt | Siehe Schritt 11 |
