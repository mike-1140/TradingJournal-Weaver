# TradingJournal installieren

Diese Anleitung richtet die Weboberfläche (TradingJournal) auf einem Rechner ein — Schritt für Schritt, mit Erklärungen, auch wenn du bisher wenig Erfahrung mit Terminal-Befehlen hast. Es gibt dazu auch eine kürzere, technischere Version:
[Technisches Handbuch: Installation: TradingJournal](../technik/60-installation-tradingjournal.md). Beide führen zum selben Ergebnis.

**Bevor du hier startest:** Die Grundausstattung (XAMPP, Composer, Node.js, ...) muss
bereits installiert sein — siehe [Windows-Grundausstattung für Einsteiger](30-windows-vorbereiten.md). Und die
Datenimport-Pipeline sollte schon eingerichtet sein — siehe
[TradingJournal-Weaver-Setup für Einsteiger](40-weaver-installieren.md).

---

## Inhalt

1. [Projekt herunterladen](#1-projekt-herunterladen)
2. [Konfigurationsdatei anlegen](#2-konfigurationsdatei-anlegen)
3. [Datenbank-Tabellen anlegen](#3-datenbank-tabellen-anlegen)
4. [Ersten Benutzer anlegen](#4-ersten-benutzer-anlegen)
5. [Optik der Seite bauen](#5-optik-der-seite-bauen)
6. [Starten und einloggen](#6-starten-und-einloggen)
7. [Praktisch: Schnellzugriff einrichten](#7-praktisch-schnellzugriff-einrichten)

---

## 1. Projekt herunterladen

Ein PowerShell-Fenster öffnen (Windows-Taste drücken, `PowerShell` eintippen, Enter) und in den Ordner wechseln, in dem auch `TradingJournal-Weaver` schon liegt (z.B. `C:\Users\<dein Name>\trading`):

```powershell
cd C:\Users\<dein Name>\trading
```

Falls das Projekt dort noch nicht liegt, herunterladen ("klonen"):

```powershell
git clone https://github.com/mike-1140/TradingJournal.git
cd TradingJournal
```

Jetzt zwei Befehle, die automatisch alle benötigten Zusatz-Bausteine herunterladen — das kann je nach Internetverbindung ein bis zwei Minuten dauern:

```powershell
composer install
npm install
```

**Falls bei `composer install` eine Fehlermeldung mit dem Wort "zip" erscheint:** Das bedeutet, eine PHP-Einstellung namens `zip` ist noch nicht aktiviert. Wie man das behebt, steht in [Windows-Grundausstattung für Einsteiger](30-windows-vorbereiten.md)
im Abschnitt "Eine PHP-Einstellung anpassen". Danach diesen Schritt hier einfach nochmal ausführen.

---

## 2. Konfigurationsdatei anlegen

Jedes Projekt braucht eine kleine Datei namens `.env`, in der z.B. die Datenbank-Zugangsdaten stehen. Diese Datei liegt **nicht** im Internet (aus Sicherheitsgründen), sondern wird lokal aus einer Vorlage erstellt:

```powershell
copy .env.example .env
php artisan key:generate
```

Jetzt die Datei `.env` im Projektordner mit einem Text-Editor öffnen (z.B. Rechtsklick →
**Öffnen mit** → **Editor**, oder in PyCharm/PhpStorm falls installiert). Darin steht ganz
oben eine Zeile `DB_CONNECTION=sqlite` — diese Zeile und die paar Zeilen danach durch Folgendes **ersetzen** (die eigenen Datenbank-Zugangsdaten von XAMPP einsetzen, siehe Windows-Grundausstattung für Einsteiger, Abschnitt "Datenbank-Passwort" — bei einer frischen XAMPP-Installation reicht meistens Benutzername `root` und ein leeres Passwort):

```env
DB_CONNECTION=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_DATABASE=ibkr_laravel
DB_USERNAME=root
DB_PASSWORD=

TRADING_DB_HOST=127.0.0.1
TRADING_DB_PORT=3306
TRADING_DB_USERNAME=root
TRADING_DB_PASSWORD=
```

Datei speichern. (Die Datenbanknamen selbst — `ibkr_money`, `ibkr_paper` usw. — müssen hier **nicht** eingetragen werden, die sind im Programm bereits fest hinterlegt.)

---

## 3. Datenbank-Tabellen anlegen

Dieser Befehl legt die Tabellen an, die die Weboberfläche selbst braucht (z.B. für den
Login):

```powershell
php artisan migrate
```

**Wichtig:** Ohne diesen Schritt gibt es später keine Login-Seite.

Die eigentlichen Handelsdaten-Tabellen kommen von einem anderen Programm (`TradingJournal-Weaver`) — die sollten laut der `TradingJournal-Weaver`-Anleitung schon angelegt worden sein. Falls nicht, jetzt nachholen (aus dem `TradingJournal-Weaver`-Ordner heraus, `<dein Name>_` durch den eigenen gewählten Namen ersetzen):

```powershell
cd ..\TradingJournal-Weaver
python -m tools.maintenance.reset_IBKR_DB money <dein Name>_
cd ..\TradingJournal
```

---

## 4. Ersten Benutzer anlegen

Zwei Befehle, nacheinander. Der erste bereitet eine kleine technische Sache vor (nur einmal nötig, auch bei mehreren Benutzern):

```powershell
php artisan setup:auth
```

(Erscheint dabei "`User ID 1 nicht gefunden`" — das ist an dieser Stelle normal und kein Fehler, weil noch kein Benutzer existiert.)

Jetzt den ersten Benutzer anlegen — Name, E-Mail und Passwort durch eigene Werte ersetzen, `<dein Name>_` durch denselben Namen wie in Schritt 3:

```powershell
php artisan auth:create-user "Dein Name" deine@mail-adresse.at "EinSicheresPasswort" --prefix=<dein Name>_ --admin
```

Das Wort `--admin` am Ende sorgt dafür, dass dieser erste Benutzer Administrator-Rechte hat (z.B. um später weitere Benutzer anzulegen).

---

## 5. Optik der Seite bauen

Dieser Befehl baut Farben, Icons und Layout der Weboberfläche zusammen:

```powershell
npm run build
```

---

## 6. Starten und einloggen

Die einfachste Variante, um die Seite auszuprobieren:

```powershell
php artisan serve
```

Danach im Browser `http://localhost:8000` öffnen und mit den in Schritt 4 vergebenen Zugangsdaten einloggen.

**Zu beachten:** Diese Variante läuft nur, solange das PowerShell-Fenster offen bleibt.
Fenster geschlossen → Seite nicht mehr erreichbar, dann `php artisan serve` erneut
eintippen.

Es gibt eine fortgeschrittenere Variante, bei der die Seite dauerhaft im Hintergrund läuft (über Apache aus dem XAMPP-Paket, mit einer eigenen Adresse wie `http://trading.local`) — das lohnt sich, wenn man die Seite oft nutzt und nicht jedes Mal ein Terminal offen haben will. Diese Einrichtung ist etwas technischer (Konfigurationsdatei bearbeiten) — Details dazu in der technischen Version [Technisches Handbuch: Installation: TradingJournal](../technik/60-installation-tradingjournal.md), Abschnitt "7. Starten, Variante B". Am besten mit etwas Erfahrung oder Unterstützung einrichten, für den Anfang reicht `php artisan serve` völlig aus.

---

## 7. Praktisch: Schnellzugriff einrichten

Damit man nicht jedes Mal manuell in den richtigen Ordner navigieren muss, gibt es ein kleines Hilfsmittel: eine Verknüpfung auf dem Desktop, die per Doppelklick direkt ein PowerShell-Fenster im richtigen Ordner öffnet.

Einmalig einrichten — im PowerShell-Fenster, das noch im `TradingJournal`-Ordner steht:

```powershell
. .\create-desktop-shortcut.ps1
```

**Falls eine Fehlermeldung mit den Worten "Ausführung von Skripts" oder "deaktiviert" erscheint:** Windows blockiert auf frisch eingerichteten Rechnern zunächst das Ausführen von `.ps1`-Dateien. Einmalig beheben — PowerShell **als Administrator** öffnen (Windows-Taste → `PowerShell` eintippen → Rechtsklick auf den Treffer → **"Als Administrator ausführen"**) und eintippen:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Danach ein normales (nicht als Administrator geöffnetes) PowerShell-Fenster im
`TradingJournal`-Ordner öffnen und den Befehl von oben nochmal ausführen.

Danach liegt auf dem Desktop eine Verknüpfung namens **"TradingJournal"**. Doppelklick darauf öffnet PowerShell direkt im richtigen Ordner — dort dann z.B. `php artisan serve` eintippen.

---

## Zusammenfassung — künftig starten

Nach der Ersteinrichtung, für den täglichen Gebrauch:

1. Doppelklick auf die Desktop-Verknüpfung "TradingJournal" (siehe Schritt 7)
2. Darin eintippen: `php artisan serve`
3. Im Browser `http://localhost:8000` öffnen

---

## Weiterführende Dokumentation

| Datei                                                | Inhalt                                                                                       |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| [Technisches Handbuch: Installation: TradingJournal](../technik/60-installation-tradingjournal.md) | Dieselben Schritte, technischer/kompakter, plus fortgeschrittene Themen (Apache-VirtualHost) |
| [Erster Start — UI-Erstkonfiguration](60-erster-start.md)                 | Was nach dem ersten Login einzustellen ist                                                   |
| [TradingJournal-Weaver-Setup](../technik/50-installation-weaver.md) | Setup der Datenimport-Pipeline |
