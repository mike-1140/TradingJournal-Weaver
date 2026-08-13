# Demo-Seed-Runbook

Erzeugt einen einmaligen, portablen `demo_seed.sql`-Dump aus anonymisierten echten
FlexQuery-Testdateien — für die öffentliche TradingJournal-Demo (Coolify-Deployment,
siehe Projekt-Memory `project_demo_hosting_plan.md`).

**Wichtig:** Alle Schritte laufen gegen eine **neue, isolierte** lokale Datenbank
`ibkr_demo` — die echte lokale `ibkr_test`/`ibkr_paper`/`ibkr_laravel` bleiben
unangetastet. Es werden **keine versionierten Konfigdateien** (`users.toml`) berührt,
nur `.env`-artige lokale Overrides (Shell-Env-Var, `.env` selbst).

**Warum `environment=test` statt `paper`:** Der normale, accountId-geroutete Import
verlangt einen passenden Eintrag in `accounts.toml` UND `users.toml` (Tabellen-Prefix
wird dort aufgelöst) — für einen Wegwerf-Demo-User müsste man dafür kurzzeitig die
versionierte `users.toml` anfassen. xml_proj hat für genau diesen Fall bereits einen
TEST-Modus (`import_ibkr_trades.py test <prefix>`), der ganz ohne accountId-Routing
funktioniert — keine Konfigdatei-Änderung nötig. Die Demo läuft dadurch technisch
unter Environment `TEST` statt `PAPER`; für eine öffentliche Demo ist das Label
zweitrangig (kann später bei Bedarf kosmetisch angepasst werden).

---

## 0. Sicherheitscheck — `incoming_mail` darf nicht mit echten Dateien belegt sein

Der TEST-Modus scannt denselben Ordner wie der produktive Import und verschiebt
**alle** `flex.*.xml`-Dateien darin nach `processed/`/`deleted/`. Vor Schritt 3 prüfen:

```powershell
Get-ChildItem C:\Trade_XML\incoming_mail\*.xml
```

Falls dort echte, noch nicht importierte FlexQuery-Dateien liegen: **abbrechen**,
zuerst den normalen Produktions-Import laufen lassen oder die Dateien vorübergehend
wegverschieben. Nur mit leerem Ordner weitermachen.

## 1. Anonymisierte Quelldateien erzeugen

```powershell
cd C:\Users\MikeDev\trading\xml_proj
.venv\Scripts\python -m tools.demo.anonymize_demo_source
```

Erzeugt `input/demo_source/*.xml` (19 Dateien, echte accountId überall durch
`DU0009999` ersetzt, Datumswerte unverändert, alle Dateinamen auf `flex.*.xml`
normalisiert — Voraussetzung für den TEST-Modus-Import). Der Ordner liegt bereits
unter der bestehenden `.gitignore`-Regel `input/`.

**Hinweis:** Die ursprünglich kuratierten `OMEX_1/2/3`-Tages-Ausschnitte wurden
durch die volle `flex.OMEX.xml`-Historie ersetzt — die isolierten Ausschnitte
setzen einen Bestand voraus, der ohne die vorangehende Historie fehlt und beim
BookTrade-Matching (`book_trades.py`) zu Raw-Zeilen ohne `dateTime` führt
(`process_ibkr_trades.py` bricht dann mit `NaTType does not support strftime` ab).

## 2. Frische, isolierte DB — `DB_NAME_TEST` umbiegen

Nur für diese PowerShell-Sitzung, nicht in `.env` schreiben:

```powershell
$env:DB_NAME_TEST = "ibkr_demo"
```

```powershell
.venv\Scripts\python -m tools.maintenance.reset_IBKR_DB test demo_
```

Legt `ibkr_demo` frisch an, alle Trading-Tabellen mit Prefix `demo_`.

## 3. Import + Verarbeitung (TEST-Modus, kein accountId-Routing)

```powershell
Copy-Item input\demo_source\*.xml C:\Trade_XML\incoming_mail\
.venv\Scripts\python -m src.import_ibkr_trades test demo_
.venv\Scripts\python -m src.process_ibkr_trades test demo_
```

Erwartete Größenordnung: ~210 Trades über alle 19 Dateien, keine Fehler im Log.
Die Quelldateien werden dabei aus `incoming_mail\` nach `C:\Trade_XML\test\demo_\processed\`
verschoben (normales Verhalten des TEST-Modus).

**Tatsächlich erzielt (2026-08-13, Referenzlauf):** 214 Trades, 45 Kampagnen (18 ACTIVE
/ 1 PENDING / 26 CLOSED — gute Durchmischung für die Demo), 99 geschlossene Trades,
217 Ledger-Zeilen, 20 offene Positionen. Keine `NULL`/`NaT`-`dateTime`-Zeilen mehr.

## 4. Laravel-Seite — eigene DB, eigener User

`trading_test` in `config/database.php` hat einen fest codierten Datenbanknamen
(`ibkr_test`) — für Migrationen/User-Anlage ist das irrelevant, die laufen auf der
**Default-Connection** (`DB_DATABASE`), nicht auf `trading_test`. Nur diese eine
Variable temporär umbiegen:

```powershell
cd ..\TradingJournal
Copy-Item .env .env.bak
# DB_DATABASE=ibkr_demo in .env eintragen (Editor oder manuell)
php artisan config:clear

php artisan migrate --force
php artisan setup:auth --admin-id=1
php artisan auth:create-user "Demo" demo@example.com "<Passwort>" --prefix=demo_ --admin
```

`setup:auth` fügt die `is_admin`-Spalte hinzu — sie ist **nicht** Teil der regulären
Migrationen, sondern wird bewusst per eigenem Command nachgerüstet (siehe Server-Deployment-
Checkliste: "nur beim allerersten Deployment"). Ohne diesen Schritt schlägt
`auth:create-user --admin` mit `Unknown column 'is_admin'` fehl. Der "User ID 1 nicht
gefunden"-Hinweis von `setup:auth` ist an dieser Stelle normal (User existiert ja noch
nicht) — betrifft nur das nachträgliche Admin-Flag-Setzen für einen bereits vorhandenen
User, hier irrelevant, da `auth:create-user --admin` das Flag gleich mitsetzt.

Zusätzlich die Psychology-Modul-Tabellen anlegen (füllt die Demo mit sinnvollen
Default-Regelwerken statt einer leeren Sektion):

```powershell
cd ..\xml_proj
.venv\Scripts\python -m tools.maintenance.setup_psychology_tables test demo_
```

Das legt `users`/`sessions`/`cache`/`psychology_*`/... frisch in `ibkr_demo` an, inkl.
genau **einem** Demo-User (kein Kontakt zu echten `mike_`/`karola_`-Usern, da komplett
andere DB).

## 5. Dump erzeugen

```powershell
mysqldump -u root --default-character-set=utf8mb4 --result-file=C:\Users\MikeDev\trading\xml_proj\tools\demo\output\demo_seed.sql ibkr_demo
```

Eine einzige, in sich geschlossene Datenbank — kein Prefix-Filtern nötig, `ibkr_demo`
enthält ausschließlich Demo-Daten. `demo_seed.sql` ist die Datei, die laut
`project_demo_hosting_plan.md` per `scp` + `docker exec ... mysql < dump.sql` auf den
Coolify-Server importiert wird. `tools/demo/output/` ist per `.gitignore` ausgeschlossen.

## 6. Verifikation (optional, ohne Config-Dateien dauerhaft anzufassen)

```powershell
mysql -u root ibkr_demo -e "SELECT COUNT(*) FROM demo_trading_campaigns; SELECT COUNT(*) FROM demo_trades_close;"
```

Für eine echte UI-Stichprobe, ohne `config/database.php` dauerhaft zu ändern, per
`php artisan tinker` **nur für die laufende Session**:

```php
config(['database.connections.trading_test.database' => 'ibkr_demo', 'database.connections.trading_test.prefix' => 'demo_']);
DB::purge('trading_test');
```
Danach lokalen Dev-Server starten, als Demo-User einloggen, TEST-Umgebung prüfen
(Dashboard, 2-3 Kampagnen-Details aus den kuratierten Szenarien).

## 7. Aufräumen

```powershell
cd ..\xml_proj
Remove-Item Env:\DB_NAME_TEST

cd ..\TradingJournal
Move-Item .env.bak .env -Force
```

`ibkr_demo` lokal optional behalten (für zukünftige Dump-Neuerstellung) oder
`DROP DATABASE ibkr_demo;` wenn nicht mehr gebraucht.
