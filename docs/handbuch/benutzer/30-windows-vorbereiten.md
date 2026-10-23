# Windows vorbereiten

Diese Anleitung erklärt Schritt für Schritt, welche Programme auf einem Windows-Rechner
installiert werden müssen, damit das Trading-Journal-Projekt läuft — **auch wenn du bisher
wenig Erfahrung mit Programmieren, Terminals oder Entwickler-Tools hast.**

Es gibt zu diesem Thema auch eine kürzere, technischere Version im technischen Handbuch:
[Installation: Windows-Grundausstattung](../technik/40-installation-windows.md). Diese Seite hier erklärt dieselben
Schritte, nur ausführlicher und mit mehr Erklärungen dazwischen. Am Ende landest du beim
gleichen Ergebnis.

**Zeitaufwand:** ca. 30–60 Minuten, je nach Internetverbindung (mehrere Programme müssen
heruntergeladen werden).

---

## Inhalt

1. [Was du am Ende hast](#1-was-du-am-ende-hast)
2. [Ein paar Begriffe vorab](#2-ein-paar-begriffe-vorab)
3. [Git installieren](#3-git-installieren)
4. [XAMPP installieren (Datenbank + Webserver)](#4-xampp-installieren-datenbank--webserver)
5. [Composer installieren](#5-composer-installieren)
6. [Node.js installieren](#6-nodejs-installieren)
7. [Python installieren](#7-python-installieren)
8. [Projektordner anlegen und Code herunterladen](#8-projektordner-anlegen-und-code-herunterladen)
9. [Alles überprüfen](#9-alles-überprüfen)
10. [Wie geht's weiter?](#10-wie-gehts-weiter)

---

## 1. Was du am Ende hast

Nach dieser Anleitung sind auf dem Rechner fünf Programme installiert:

| Programm | Wofür |
|---|---|
| **Git** | Lädt den Programmcode von GitHub herunter und hält ihn aktuell |
| **XAMPP** | Enthält die Datenbank (MySQL), die Programmiersprache PHP und einen Webserver (Apache, für den Anfang nicht nötig) |
| **Composer** | Installiert Zusatz-Bausteine für den PHP-Teil des Projekts |
| **Node.js** | Baut die Optik (CSS/JavaScript) der Weboberfläche |
| **Python** | Führt die Import-Skripte aus, die die Handelsdaten von Interactive Brokers holen und verarbeiten |

Außerdem liegen am Ende zwei Ordner mit dem eigentlichen Projekt-Code auf der Festplatte.

---

## 2. Ein paar Begriffe vorab

Diese Begriffe tauchen im Folgenden immer wieder auf — kurz erklärt, damit nichts wie
"Fachchinesisch" wirkt:

- **PowerShell / Terminal**: Ein Fenster, in das man statt mit der Maus zu klicken, Befehle
  als Text eintippt und mit Enter bestätigt. Wirkt zuerst ungewohnt, ist aber nur eine
  andere Art, dem Computer zu sagen, was er tun soll. Wie man es öffnet, steht in Schritt 8.
- **Installer**: Eine `.exe`-Datei, die man herunterlädt und doppelklickt — startet einen
  Installationsassistenten mit "Weiter"-Buttons, wie bei jedem anderen Programm auch.
- **Git / Repository / "klonen"**: Der Programmcode für dieses Projekt liegt online auf
  [GitHub](https://github.com) in zwei separaten "Repositories" (Projektordnern mit
  Versionsverlauf). "Klonen" bedeutet: eine komplette Kopie davon auf den eigenen Rechner
  herunterladen.
- **PATH**: Eine Liste von Ordnern, in denen Windows automatisch nach Programmen sucht,
  wenn man im Terminal nur den Programmnamen eintippt (z.B. `php` statt dem kompletten
  Pfad `C:\xampp\php\php.exe`). Diese Liste muss man XAMPP nach der Installation manuell
  hinzufügen — das erklärt Schritt 4.

**Wichtiger Tipp für die ganze Anleitung:** Befehle, die in einem grauen Kasten stehen,
immer **exakt so abtippen oder besser kopieren** (Rechtsklick → Kopieren, dann im
Terminal-Fenster Rechtsklick → Einfügen). Groß-/Kleinschreibung und Sonderzeichen spielen
eine Rolle.

---

## 3. Git installieren

1. Diese Seite öffnen: [git-scm.com/install/windows](https://git-scm.com/install/windows) und
   auf **„Click here to download“** klicken — das lädt den Installer für einen normalen
   64-Bit-Windows-Rechner herunter. Der Download startet **nicht** von selbst.
2. Die heruntergeladene Datei doppelklicken, um die Installation zu starten.
3. Durch den Installationsassistenten klicken. Bei der Seite mit der Überschrift
   **"Adjusting your PATH environment"** die Option **"Git from the command line and also
   from 3rd-party software"** auswählen (meistens schon vorausgewählt).
4. Bei allen anderen Seiten die vorausgewählte Option ("Next") übernehmen, bis die
   Installation fertig ist.

Für das Herunterladen und spätere Aktualisieren des Codes ist sonst nichts einzurichten — auch
kein GitHub-Konto.

> [!NOTE]
> Nur wer später selbst Änderungen am Code einreichen möchte, sollte Git noch Namen und
> Mailadresse mitteilen (PowerShell: `git config --global user.name "Dein Name"` und
> `git config --global user.email "deine@mail-adresse.at"`). Für die normale Nutzung ist das
> nicht nötig.

---

## 4. XAMPP installieren (Datenbank + Webserver)

XAMPP bringt in einem Paket drei Dinge mit: **MySQL** (die Datenbank, in der alle
Handelsdaten gespeichert werden), **PHP** (die Programmiersprache, in der die Weboberfläche
geschrieben ist) und **Apache** (ein Webserver). Gebraucht werden zunächst nur MySQL und PHP —
die Weboberfläche startet später mit einem eigenen, eingebauten Mini-Webserver. Apache ist nur
für eine fortgeschrittene Variante nötig (Kapitel [TradingJournal
installieren](50-tradingjournal-installieren.md), Abschnitt „Starten und öffnen“).

**Wichtig bei der Auswahl:** Auf der Download-Seite gibt es mehrere Versionen nebeneinander.
Für dieses Projekt wird **PHP Version 8.2 oder neuer** gebraucht — also die
**"8.2.x"-Version** (oder eine neuere Zahl) auswählen, nicht blind irgendeine.

> [!NOTE]
> Das PHP in XAMPP veraltet mit der Zeit: XAMPP liefert neue PHP-Versionen oft erst Wochen nach
> einem Sicherheitsupdate aus. Bei einer bekannt gewordenen PHP-Sicherheitslücke lässt sich PHP
> auch selbst austauschen — siehe [Updates einspielen](80-updates.md), Abschnitt
> „Sicherheitsupdates für PHP“.

### Installieren

1. Seite öffnen: [apachefriends.org](https://www.apachefriends.org/)
2. Installer für die passende PHP-Version (siehe oben) herunterladen und doppelklicken.
3. Bei der Frage nach den Komponenten mindestens **Apache**, **MySQL** und **PHP**
   angehakt lassen — den Rest (FileZilla, Mercury Mail, Tomcat) kann man abwählen, wird
   nicht gebraucht.
4. Als Installationsordner den vorgeschlagenen Pfad `C:\xampp` übernehmen.
5. Installation abschließen, XAMPP am Ende **nicht sofort starten** (Häkchen ggf. entfernen)
   — der nächste Schritt kümmert sich darum.

### XAMPP starten

1. **XAMPP Control Panel** über das Startmenü öffnen.
2. Rechts neben **MySQL** auf **Start** klicken. Die Zeile sollte kurz danach grün hinterlegt
   sein und "Running" anzeigen. **Apache** muss nicht gestartet werden.

### PHP für das Terminal verfügbar machen

Ohne diesen Schritt kennt das Terminal die Befehle `php` und `composer` nicht.

1. Windows-Taste drücken, `Umgebungsvariablen` eintippen, **"Umgebungsvariablen für dieses
   Konto bearbeiten"** öffnen.
2. Im oberen Bereich ("Benutzervariablen") die Zeile **`Path`** anklicken (einmal, nicht
   doppelt), dann auf **Bearbeiten** klicken.
3. Auf **Neu** klicken, dann eintippen: `C:\xampp\php`
4. Nochmal auf **Neu** klicken, dann eintippen: `C:\xampp\mysql\bin`
5. Überall auf **OK** klicken, um die Fenster zu schließen.
6. **Wichtig:** Alle offenen PowerShell-Fenster schließen — die Änderung wirkt erst in
   einem neu geöffneten Fenster.

**Testen:** Neues PowerShell-Fenster öffnen, `php -v` eintippen und Enter drücken. Es sollte
etwas wie `PHP 8.2.x` angezeigt werden. Kommt stattdessen eine Fehlermeldung, Schritt 3–6
nochmal genau durchgehen.

### Eine PHP-Einstellung anpassen ("zip"-Erweiterung)

Dieser Schritt ist wichtig, aber leicht zu übersehen — XAMPP hat eine Funktion namens `zip`
standardmäßig **ausgeschaltet**, die später beim Einrichten der Weboberfläche gebraucht
wird. Ohne diesen Schritt kommt dort eine Fehlermeldung mit dem Wort "zip" darin.

1. Den Datei-Explorer öffnen und zu `C:\xampp\php` navigieren.
2. Die Datei **`php.ini`** mit einem Text-Editor öffnen (Rechtsklick → **Öffnen mit** →
   **Editor**).
3. Im Editor mit `Strg+F` nach `zip` suchen. Es sollte eine Zeile erscheinen, die so aussieht:
   `;extension=zip`
4. Das Semikolon (`;`) ganz am Anfang dieser einen Zeile löschen, sodass nur noch
   `extension=zip` dasteht. Sonst nichts an der Zeile verändern.
5. Datei speichern (`Strg+S`) und den Editor schließen.
6. Ein **neues** PowerShell-Fenster öffnen (wichtig: ein neues, kein altes weiterverwenden)
   und eintippen: `php -m`. In der langen Liste, die erscheint, sollte irgendwo `zip` stehen.

### XAMPP automatisch starten lassen (optional, aber empfohlen)

Ohne diesen Schritt muss man vor jeder Nutzung erst das XAMPP Control Panel öffnen und
MySQL manuell starten. Mit diesem Schritt startet die Datenbank automatisch mit Windows — das
ist auch für den automatischen täglichen Datenimport wichtig, der eine laufende Datenbank
braucht.

1. XAMPP Control Panel schließen, dann über das Startmenü erneut öffnen — diesmal per
   **Rechtsklick** auf das XAMPP-Symbol → **"Als Administrator ausführen"**.
2. Ganz links in der Zeile **MySQL** gibt es eine kleine Spalte **"Svc"** — dort das
   Kästchen anklicken.
3. Meist erscheint jetzt ein Fenster der **Benutzerkontensteuerung** von Windows („Möchten Sie
   zulassen, dass durch diese App Änderungen an Ihrem Gerät vorgenommen werden?“). Das ist
   normal, weil MySQL dabei als Windows-Dienst eingerichtet wird — mit **Ja** bestätigen.

Falls das nicht klappt: kein Problem, XAMPP funktioniert auch ohne diesen Schritt — dann
einfach vor jeder Nutzung kurz das Control Panel öffnen und MySQL starten.

### Datenbank-Passwort

Nach einer frischen XAMPP-Installation hat die Datenbank einen Benutzer namens `root` **ohne
Passwort**. Für die lokale Nutzung auf dem eigenen Rechner ist das in Ordnung — diese
Datenbank ist nicht aus dem Internet erreichbar. Dieser leere Wert wird später beim
Einrichten des eigentlichen Projekts (in einer Datei namens `.env`) einfach so übernommen.

---

## 5. Composer installieren

Composer lädt automatisch alle Zusatz-Bausteine, die der Weboberflächen-Teil des Projekts
braucht.

1. Seite öffnen: [getcomposer.org/download](https://getcomposer.org/download/)
2. Datei **`Composer-Setup.exe`** herunterladen und doppelklicken.
3. Der Installer erkennt PHP normalerweise automatisch (weil es ja schon installiert ist).
   Falls nachgefragt wird, wo PHP liegt: `C:\xampp\php\php.exe` eintragen.
4. Restliche Schritte mit "Weiter" durchklicken.

**Testen:** Neues PowerShell-Fenster öffnen, `composer -V` eintippen. Es sollte eine
Versionsnummer erscheinen.

---

## 6. Node.js installieren

Node.js wird gebraucht, um die Optik (Farben, Icons, Layout) der Weboberfläche
zusammenzubauen.

1. Seite öffnen: [nodejs.org](https://nodejs.org/)
2. Die als **"LTS"** gekennzeichnete Version herunterladen (das ist die empfohlene,
   stabilste Version) und installieren — überall die Standardeinstellungen übernehmen.

**Testen:** Neues PowerShell-Fenster öffnen, `node -v` und danach `npm -v` eintippen — beide
sollten eine Versionsnummer anzeigen. Bei `node -v` muss sie **mindestens v20.19** sein (die
aktuelle LTS-Version erfüllt das); ältere Versionen können die Optik nicht bauen.

---

## 7. Python installieren

Python führt die Skripte aus, die die Handelsdaten von Interactive Brokers abrufen und in
die Datenbank einsortieren.

Gebraucht wird **Python 3.14** — nicht die neueste Version, die python.org gerade ganz oben
anbietet. Mit einer neueren Version (z. B. 3.15) lassen sich einige Zusatz-Pakete, die
`TradingJournal-Weaver` braucht, noch nicht installieren.

1. Seite öffnen: [python.org/downloads/windows](https://www.python.org/downloads/windows/)
2. In der Liste den obersten Eintrag mit **Python 3.14** suchen (z. B. *Python 3.14.8 - Sept.
   30, 2026*) und dort auf **„Windows installer (64-bit)“** klicken. Das ist der eigenständige
   Installer (*standalone installer*).
3. Die heruntergeladene Datei doppelklicken.

> [!WARNING]
> **Nicht** den *Python install manager* verwenden, der auf python.org ebenfalls angeboten wird,
> und auch nicht den großen Knopf *Download Python 3.x* auf der Startseite der Downloads — beide
> installieren die jeweils neueste Version. Diese Anleitung geht vom eigenständigen Installer
> für Python 3.14 aus.

4. **Ganz wichtig, leicht zu übersehen:** Ganz unten auf der ersten Installer-Seite gibt es
   eine Checkbox **"Add python.exe to PATH"** — die **muss angehakt sein**, bevor man auf
   "Install Now" klickt. Ohne diesen Haken funktioniert `python` später nicht im Terminal.
5. Installation abschließen.

**Testen:** Neues PowerShell-Fenster öffnen, `python --version` eintippen — sollte
`Python 3.14.x` anzeigen. Mit dieser Version ist das Projekt getestet.

---

## 8. Projektordner anlegen und Code herunterladen

### Terminal öffnen und Startordner verstehen

Ein neu geöffnetes PowerShell-Fenster startet **nicht immer am selben Ort** — meistens im
eigenen Benutzerordner (`C:\Users\<dein Anmeldename>`), aber wenn man es über "Als
Administrator ausführen" öffnet, landet man stattdessen in einem Systemordner
(`C:\Windows\System32`). Falls du dich also mal wunderst, warum du "irgendwo landest": das
ist normal, kein Fehler.

Man kann jederzeit mit dem Befehl `cd` in einen anderen Ordner wechseln, z.B.:
```powershell
cd C:\Users\<dein Anmeldename>
```
(`<dein Anmeldename>` durch den eigenen Windows-Anmeldenamen ersetzen — der steht z.B. oben
im Startmenü.)

### Projektordner anlegen

Ein neues PowerShell-Fenster öffnen (normal, **nicht** als Administrator) und folgende zwei
Zeilen eintippen:

```powershell
New-Item -ItemType Directory -Force -Path C:\Users\<dein Anmeldename>\trading
Set-Location C:\Users\<dein Anmeldename>\trading
```

Die erste Zeile legt einen neuen, leeren Ordner namens `trading` an. Die zweite wechselt
dort hinein — alle folgenden Befehle in diesem Fenster beziehen sich jetzt auf diesen
Ordner. (Der Name/Ort dieses Ordners ist frei wählbar — `trading` ist nur ein Vorschlag.)

### Die zwei Projekte herunterladen ("klonen")

Jetzt die folgenden zwei Befehle **einzeln, nacheinander** eintippen (nach jeder Zeile
Enter drücken und warten, bis der Download fertig ist, bevor die nächste Zeile kommt):

```powershell
git clone https://github.com/mike-1140/TradingJournal-Weaver.git
```
```powershell
git clone https://github.com/mike-1140/TradingJournal.git
```

Die Repositories sind öffentlich — eine Anmeldung bei GitHub ist dafür nicht nötig.

**Ergebnis:** Im Ordner `trading` liegen jetzt zwei Unterordner: `TradingJournal-Weaver` und
`TradingJournal`. Das lässt sich mit folgendem Befehl überprüfen — er
listet den Inhalt des aktuellen Ordners auf:

```powershell
Get-ChildItem
```

---

## 9. Alles überprüfen

Ein **neues** PowerShell-Fenster öffnen (wichtig: neu, nicht dasselbe wie vorher weiterverwenden)
und der Reihe nach eintippen — nach jeder Zeile sollte eine Versionsnummer erscheinen, keine
Fehlermeldung:

```powershell
git --version
php -v
composer -V
node -v
npm -v
python --version
```

Zusätzlich: XAMPP Control Panel öffnen und prüfen, dass **MySQL** grün ("Running") angezeigt
wird.

Falls bei einem dieser Befehle eine Fehlermeldung kommt (z.B. "wird nicht als Befehl
erkannt"): meistens bedeutet das, dass entweder die Installation noch nicht komplett ist,
oder dass die PATH-Änderung (Schritt 4) noch nicht wirkt, weil das Terminal-Fenster zu alt
ist — ein frisches Fenster öffnen und nochmal probieren.

---

## 10. Wie geht's weiter?

Die Grundausstattung ist fertig. Als Nächstes folgen die eigentlichen Projekt-Einrichtungen
— dort geht es dann konkret um dieses Trading-Journal-Projekt (Datenbank befüllen, erste
Anmeldung usw.):

1. [TradingJournal-Weaver installieren](40-weaver-installieren.md) — Einrichtung der
   Datenimport-Pipeline
2. [TradingJournal installieren](50-tradingjournal-installieren.md) — Einrichtung
   der Weboberfläche, ebenfalls für Einsteiger erklärt
3. [Erster Start — UI-Erstkonfiguration](60-erster-start.md) — erste Schritte in der Weboberfläche
