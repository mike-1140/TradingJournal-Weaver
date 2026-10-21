# Updates einspielen

Wie eine bestehende Installation — auf dem eigenen PC oder auf einem Server — auf den neuesten
Stand von TradingJournal-Weaver und TradingJournal kommt. Für die Erstinstallation siehe
[TradingJournal-Weaver installieren](40-weaver-installieren.md) und [TradingJournal
installieren](50-tradingjournal-installieren.md).

## Was ein Update macht — und was nicht

Ein Update holt den neuen Code von GitHub und erledigt alles, was danach nötig ist, damit er
läuft: neue Programmbausteine (Python, PHP, JavaScript) installieren, kleine Anpassungen an den
Datenbank-Tabellen vornehmen, die Weboberfläche neu bauen.

**Deine Daten bleiben unangetastet:** Trades, Kampagnen, Log, Psychologie und Kontostände
werden nicht neu aufgebaut, `reset_IBKR_DB.py` ist für ein Update nie nötig. Ebenso bleiben
deine eigenen Einstellungsdateien unverändert — die beiden `.env`-Dateien, `users.toml`,
`accounts.toml` und `pipeline.toml`.

## Update starten

Das Skript `update.ps1` im Ordner `TradingJournal` erledigt alle Schritte in der richtigen
Reihenfolge — für **beide** Programme.

1. Vorher sicherstellen, dass gerade **kein Lauf** von `run_pipeline.py` aktiv ist.
2. **[PowerShell]** in den Ordner `TradingJournal` wechseln (Pfad an die eigene Installation
   anpassen) und das Skript starten:

   ```powershell
   cd C:\Users\<dein Anmeldename>\trading\TradingJournal
   .\update.ps1
   ```

3. Am Ende steht in grün `=== Update abgeschlossen: … ===`. Danach im Browser die Seite neu
   laden.

Voraussetzung: `TradingJournal-Weaver` und `TradingJournal` liegen nebeneinander im selben
Ordner — so wie bei der Installation. Meldet PowerShell, dass das Ausführen von Skripts
deaktiviert ist, hilft derselbe einmalige Schritt wie beim Einrichten der Desktop-Verknüpfung
([TradingJournal-Weaver installieren](40-weaver-installieren.md), Schritt 7).

**Neu starten muss man danach nichts** — weder `php artisan serve` noch Apache. Die Weboberfläche
liest den neuen Stand beim nächsten Seitenaufruf.

**Auf einem Server** genauso, nur vorher per Fernzugriff (RDP o. ä., siehe Technisches Handbuch
[Server-Betrieb — TradingJournal auf einem eigenen Server](../technik/70-server-betrieb.md)) auf
den Server verbinden und dort im Ordner `TradingJournal` `.\update.ps1` starten.

## Was das Skript im Einzelnen tut

1. **Code holen** — `git pull` in `TradingJournal-Weaver` und in `TradingJournal`
2. **Python-Pakete** für TradingJournal-Weaver aktualisieren (`pip install -r requirements.txt`
   in dessen Arbeitsumgebung)
3. **Datenbank-Anpassungen** — die Skripte `TradingJournal-Weaver/dev/migrate_*.py` ausführen;
   sie ergänzen fehlende Spalten oder Tabellen und überspringen, was schon da ist
4. **PHP- und JavaScript-Pakete** installieren und die Weboberfläche neu bauen (`composer
   install`, `npm install`, `npm run build`)
5. **Laravel-Tabellen** aktualisieren (`php artisan migrate --force`, z. B. die Benutzer)
6. **Zwischenspeicher** von Laravel leeren und neu aufbauen
7. **Versionsstand** notieren, damit die App ihn anzeigen kann (siehe unten)

Geht ein Schritt schief, **bricht das Skript sofort ab** und sagt, wo — statt mit einem halb
aktualisierten Stand weiterzumachen. Einzige Ausnahme sind die Datenbank-Anpassungen aus
Schritt 3: Sie melden ein Problem als gelbe Warnung, und das Skript läuft weiter — die Warnung
dann trotzdem ernst nehmen. Nach dem Beheben einfach `.\update.ps1` noch einmal
starten; alle Schritte lassen sich gefahrlos wiederholen.

## Nach dem Update: neue Einstellungen?

Neue Versionen bringen manchmal zusätzliche, **optionale** Einstellungen mit (z. B.
`MAX_GAP_DAYS` für die Kampagnen-Frist). Sie stehen in den Vorlagen `.env.example` der beiden
Programme, landen aber nicht automatisch in der eigenen `.env`. Wer eine neue Einstellung nutzen
möchte, überträgt die Zeile von Hand. Ohne Eintrag gilt jeweils der bisherige Standard.

## Sicherheitsupdates für PHP

`update.ps1` aktualisiert nur TradingJournal und TradingJournal-Weaver, nicht die Programme
darunter. PHP kommt bei einer XAMPP-Installation mit XAMPP mit — und XAMPP liefert neue
PHP-Versionen oft erst Wochen nach einem Sicherheitsupdate aus. Wird eine kritische PHP-Lücke
bekannt (Ankündigungen unter [php.net](https://www.php.net/) → *News*), lässt sich PHP auch
selbst austauschen, ohne auf ein neues XAMPP zu warten. Die Schritt-für-Schritt-Anleitung steht
im technischen Handbuch ([Installation: Windows-Grundausstattung](../technik/40-installation-windows.md),
Abschnitt „PHP aktualisieren, ohne auf ein neues XAMPP zu warten“).

Welche PHP-Version gerade läuft — **[PowerShell]:**

```powershell
php -v
```

## Welche Version läuft gerade?

Unten in der Seitenleiste der App steht **Build:** mit einer kurzen Kennung (z. B.
`Build: e1db712`); fährt man mit der Maus darüber, erscheinen Versionsbezeichnung und
Zeitpunkt des Updates. Die Anzeige erscheint erst nach dem **ersten** Lauf von `update.ps1` —
direkt nach der Installation ist dort noch nichts zu sehen.

Ohne App nachsehen — **[PowerShell]** im Ordner `TradingJournal`:

```powershell
git describe --tags --always
```

## Wenn etwas schiefgeht

| Problem | Ursache | Lösung |
|---|---|---|
| `git pull` schlägt fehl | Im Ordner wurden Dateien geändert, die auch das Update ändert, oder es liegt eine gleichnamige neue Datei im Weg | **[PowerShell]** im genannten Ordner `git status` — eigene Änderungen sichern (`git stash`) oder die störende Datei umbenennen, dann `.\update.ps1` erneut starten |
| `pip install`, `composer install` oder `npm install` schlägt fehl | Fehlendes Programm bzw. fehlende PHP-Erweiterung, oder keine Internetverbindung | Die Fehlermeldung nennt meist die Ursache; Grundausstattung prüfen ([Windows vorbereiten](30-windows-vorbereiten.md)) |
| `php artisan migrate --force` meldet einen Fehler | Die Datenbank wurde von Hand verändert und passt nicht zur erwarteten Struktur | Fehlermeldung lesen; vor einem weiteren Versuch ein Datenbank-Backup ziehen |
| Die Seite zeigt nach dem Update noch den alten Stand | Der Browser zeigt eine zwischengespeicherte Fassung | Seite mit **Strg + Shift + R** neu laden; prüfen, ob `npm run build` ohne Fehler durchlief |
| Ein Update verlangt eine neue Python- oder PHP-Version bzw. -Erweiterung | Das kann das Skript nicht selbst installieren | Wie bei der Ersteinrichtung nachinstallieren ([Windows vorbereiten](30-windows-vorbereiten.md)), dann `.\update.ps1` erneut starten |
