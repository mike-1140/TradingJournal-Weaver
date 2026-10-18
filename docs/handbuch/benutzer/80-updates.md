# Updates einspielen

Beschreibt, wie du eine bestehende Installation (lokaler PC oder eigener Server, siehe
[Technisches Handbuch: Server-Betrieb — TradingJournal auf einem eigenen Server](../technik/70-server-betrieb.md)) auf den neuesten Stand von
TradingJournal-Weaver + TradingJournal bringst. Für die Erstinstallation siehe stattdessen
[Technisches Handbuch: Installation: TradingJournal-Weaver](../technik/50-installation-weaver.md)/
[Technisches Handbuch: Installation: TradingJournal](../technik/60-installation-tradingjournal.md).

## Was "Update" hier bedeutet

Neuer Code aus GitHub (`git pull`) + alles, was danach nötig ist, damit er auch wirklich
läuft: neue Python-/Composer-/npm-Abhängigkeiten installieren, neue Datenbank-Migrationen
anwenden (sowohl Laravel-eigene als auch die kleinen `TradingJournal-Weaver/dev/migrate_*.py`-Skripte),
Frontend neu bauen (Vite), Laravel-Caches neu aufbauen. **Kein** Neuaufbau der
Trading-Datenbanken selbst — die bleiben unangetastet, `reset_IBKR_DB.py` ist für Updates
nie nötig.

## Automatisiert — `update.ps1`

Im TradingJournal-Repo liegt ein fertiges Skript, das alle nötigen Schritte in der
richtigen Reihenfolge ausführt:

```powershell
cd TradingJournal
.\update.ps1
```

Voraussetzung: `TradingJournal-Weaver` liegt als Geschwister-Verzeichnis neben `TradingJournal` (genau
wie bei der Installation, siehe README). Das Skript bricht bei jedem Fehler sofort mit
einer klaren Meldung ab, statt mit einem halbaktualisierten Stand weiterzumachen — meist
ist die Ursache ein `git pull`-Konflikt durch lokale, nicht committete Änderungen
(`git status`/`git stash` im betroffenen Repo prüfen, dann `update.ps1` erneut starten).

**Was das Skript macht** (Kurzfassung, siehe Kommentare im Skript für Details):
1. `git pull` in beiden Repos
2. Python-Abhängigkeiten (`pip install -r requirements.txt`)
3. `TradingJournal-Weaver/dev/migrate_*.py`-Skripte (idempotent, überspringen bereits vorhandene Spalten)
4. Composer- + npm-Abhängigkeiten, `npm run build` (Frontend-Assets)
5. `php artisan migrate --force` (Laravel-eigene Tabellen wie `users`)
6. Laravel-Caches neu aufbauen (`config:cache`, `route:cache`, `view:cache`)
7. Aktuelle Version in `storage/app/version.json` schreiben — erscheint danach in der
   Sidebar der App

## Update auf dem lokalen PC

Direkt wie oben beschrieben — Terminal öffnen, ins `TradingJournal`-Verzeichnis wechseln,
`.\update.ps1` ausführen. Kein Neustart von irgendetwas nötig (kein eigener Webserver-Prozess
läuft dauerhaft im Hintergrund, `php artisan serve`/dein lokaler Webserver liest Code und
Caches bei jedem Request neu).

## Update auf dem Server

Gleicher Ablauf, nur zuerst per Remote-Zugriff (RDP, RustDesk o. ä. — siehe
[Technisches Handbuch: Server-Betrieb — TradingJournal auf einem eigenen Server](../technik/70-server-betrieb.md)) auf den Server verbinden. Dort:

```powershell
cd C:\trading\TradingJournal
.\update.ps1
```

**Kein Apache-Neustart nötig** — weder `httpd.conf` noch geladene PHP-Module ändern sich
durch ein normales Code-Update; `php artisan config:cache`/`route:cache`/`view:cache`
überschreiben die Cache-Dateien direkt, Apache/PHP liest sie beim nächsten Request
automatisch neu ein.

**Ausnahme:** Falls eine neue TradingJournal-Weaver-Version zusätzliche Python-Pakete braucht, die noch
nicht in `requirements.txt` standen, oder falls `httpd.conf`/`php.ini` manuell angepasst
werden müssen (z. B. eine neue PHP-Extension wird plötzlich vorausgesetzt) — das würde das
Skript nicht automatisch erledigen, dann Schritt für Schritt wie in
„Technisches Handbuch: Server-Betrieb — TradingJournal auf einem eigenen Server“ nachbessern.

## Umbenennung: `xml_proj` → `TradingJournal-Weaver` (einmalig, Oktober 2026)

Das Repo für den Datenimport hieß früher `xml_proj`. Wer es noch unter dem alten Namen
installiert hat, passt eine bestehende Installation **einmalig** an — auf jedem Rechner, auf dem
es liegt (lokaler PC, Server, Rechner für den verteilten Abruf). Erst danach `update.ps1`
ausführen: Das neue Skript sucht den Ordner bereits unter dem neuen Namen.

Vorher alle Programme schließen, die im Ordner arbeiten (PyCharm, Terminals, Explorer-Fenster),
sonst lässt Windows das Umbenennen nicht zu.

1. **[PowerShell]** Ordner umbenennen und die Adresse des GitHub-Repos aktualisieren
   (Pfad `C:\trading` ggf. an die eigene Installation anpassen):

   ```powershell
   cd C:\trading
   Rename-Item xml_proj TradingJournal-Weaver
   cd TradingJournal-Weaver
   git remote set-url origin https://github.com/mike-1140/TradingJournal-Weaver.git
   ```

2. **[PowerShell]** Python-Umgebung neu anlegen — eine verschobene `.venv` funktioniert nicht
   zuverlässig, weil sie den alten Pfad fest enthält:

   ```powershell
   Remove-Item -Recurse -Force .venv
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   pip install -e ../shared_python
   ```

3. **[Windows-Aufgabenplanung]** Falls der tägliche Lauf als geplante Aufgabe eingerichtet ist:
   die Aufgabe öffnen und unter *Aktionen* Programmpfad und *Starten in* von `…\xml_proj` auf
   `…\TradingJournal-Weaver` ändern.

4. **[PowerShell]** Desktop-Verknüpfung erneuern (falls vorhanden): die alte
   „xml_proj Pipeline“ löschen und im Ordner `TradingJournal-Weaver` neu anlegen:

   ```powershell
   .\create-desktop-shortcut.ps1
   ```

5. **[PowerShell]** Prüfen, dass alles läuft — der Trockenlauf zeigt die Schritte, ohne etwas
   zu verändern:

   ```powershell
   python run_pipeline.py --dry-run
   ```

Die Datenordner `C:\Trade_XML\…` und `C:\Trade_CSV\…`, die `.env`, `pipeline.toml` und
`accounts.toml` bleiben unverändert — sie ziehen mit dem Ordner einfach mit.

## Welche Version läuft gerade?

Nach einem `update.ps1`-Lauf steht die aktuelle Version (Git-Tag + Kurz-Hash + Zeitpunkt)
in der TradingJournal-Sidebar. Manuell nachsehen:

```powershell
cd TradingJournal
git describe --tags --always
git rev-parse --short HEAD
```

## Troubleshooting

| Problem | Ursache | Lösung |
|---|---|---|
| `git pull` schlägt fehl | Lokale, nicht committete Änderungen oder kollidierende untracked Dateien | `git status`/`git diff` im betroffenen Repo prüfen, Änderungen sichern (`git stash`) oder committen |
| `pip install`/`composer install`/`npm install` schlägt fehl | Fehlende Systemvoraussetzung, oder Netzwerkproblem | Fehlermeldung lesen — meist eindeutig (fehlende Extension, Versionskonflikt); `setup/*-setup.md` für Grundvoraussetzungen prüfen |
| `php artisan migrate --force` meldet Fehler | Migration setzt eine Spalte voraus, die schon anders existiert (z. B. bei sehr alten, manuell angepassten Installationen) | Fehlermeldung + betroffene Migration in `database/migrations/` ansehen, im Zweifel vor dem nächsten Update-Versuch ein Datenbank-Backup ziehen |
| Seite zeigt nach dem Update einen alten Zustand | Browser-Cache oder alte Vite-Assets | Hard-Reload im Browser (`Strg+Shift+R`); prüfen, dass `npm run build` im Skript-Log erfolgreich durchlief |
