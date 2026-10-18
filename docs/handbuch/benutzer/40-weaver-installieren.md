# TradingJournal-Weaver installieren

Diese Anleitung richtet die Datenimport-Pipeline (`TradingJournal-Weaver`) auf einem Rechner ein — sie
holt die Handelsdaten von Interactive Brokers und verarbeitet sie für das Trading-Journal.
Schritt für Schritt, mit Erklärungen, auch wenn du bisher wenig Erfahrung mit
Terminal-Befehlen oder Python hast. Es gibt dazu auch eine kürzere, technischere Version:
[Technisches Handbuch: Installation: TradingJournal-Weaver](../technik/50-installation-weaver.md). Beide führen zum selben Ergebnis.

**Bevor du hier startest:** Die Grundausstattung (Git, Python, XAMPP, ...) muss bereits
installiert sein — siehe [Windows vorbereiten](30-windows-vorbereiten.md).

---

## Inhalt

1. [Projekt herunterladen](#1-projekt-herunterladen)
2. [Python-Arbeitsumgebung einrichten](#2-python-arbeitsumgebung-einrichten)
3. [Gemeinsame Bausteine installieren](#3-gemeinsame-bausteine-installieren)
4. [Konfigurationsdatei anlegen](#4-konfigurationsdatei-anlegen)
5. [Datenbank-Tabellen anlegen](#5-datenbank-tabellen-anlegen)
6. [Automatisierung einrichten](#6-automatisierung-einrichten)
7. [Ersten Testlauf machen](#7-ersten-testlauf-machen)
8. [Praktisch: Schnellzugriff einrichten](#8-praktisch-schnellzugriff-einrichten)

---

## 1. Projekt herunterladen

Ein PowerShell-Fenster öffnen (Windows-Taste drücken, `PowerShell` eintippen, Enter) und in
den Ordner wechseln, in dem die anderen Projekte schon liegen bzw. liegen sollen (z.B.
`C:\Users\<dein Name>\trading`):

```powershell
cd C:\Users\<dein Name>\trading
```

Falls `TradingJournal-Weaver` dort noch nicht liegt, herunterladen ("klonen"):

```powershell
git clone https://github.com/mike-1140/TradingJournal-Weaver.git
cd TradingJournal-Weaver
```

**Wichtig für später:** `TradingJournal-Weaver` muss als **Geschwisterordner** neben einem Ordner namens
`shared_python` liegen (also beide direkt im selben übergeordneten Ordner, nicht
ineinander verschachtelt) — Schritt 3 unten braucht das. Falls `shared_python` noch fehlt:

```powershell
cd ..
git clone https://github.com/mike-1140/shared_python.git
cd TradingJournal-Weaver
```

---

## 2. Python-Arbeitsumgebung einrichten

Python-Projekte arbeiten normalerweise mit einer eigenen, abgeschotteten "Arbeitsumgebung"
(venv — kurz für *virtual environment*) pro Projekt. Das verhindert, dass sich verschiedene
Python-Projekte auf demselben Rechner gegenseitig mit unterschiedlichen Versionen von
Zusatz-Paketen in die Quere kommen. Drei Befehle, nacheinander:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Der zweite Befehl "aktiviert" die Arbeitsumgebung für dieses Terminal-Fenster — am
vorangestellten `(.venv)` im Prompt erkennbar. Der dritte lädt alle Zusatz-Pakete herunter,
die `TradingJournal-Weaver` braucht (kann ein bis zwei Minuten dauern).

**Wichtig:** Die Aktivierung (`.venv\Scripts\activate`) gilt nur für das aktuell offene
Terminal-Fenster. Bei jedem neuen Fenster muss man diesen einen Befehl wiederholen — dafür
gibt es aber eine Abkürzung, siehe Schritt 8.

---

## 3. Gemeinsame Bausteine installieren

`TradingJournal-Weaver` nutzt einige Hilfsfunktionen (z.B. für Dezimalzahlen-Rechnung), die in einem
zweiten, gemeinsam genutzten Ordner (`shared_python`) liegen. Dieser Befehl verknüpft beide
Ordner miteinander:

```powershell
pip install -e ../shared_python
```

Funktioniert nur, wenn `shared_python` wirklich als Geschwisterordner neben `TradingJournal-Weaver`
liegt (siehe Schritt 1). Falls dabei ein Fehler mit dem Wort `BackendUnavailable` erscheint:
das ist ein bekanntes, seltenes Problem — in dem Fall Bescheid geben, das lässt sich lösen.

---

## 4. Konfigurationsdatei anlegen

Wie beim Trading-Journal selbst braucht auch `TradingJournal-Weaver` eine `.env`-Datei mit den eigenen
Zugangsdaten. Vorlage kopieren:

```powershell
copy .env.example .env
```

Jetzt die neue Datei `.env` im `TradingJournal-Weaver`-Ordner mit einem Text-Editor öffnen (Rechtsklick →
**Öffnen mit** → **Editor**). Folgende Werte eintragen bzw. anpassen:

| Zeile in `.env` | Was dort rein muss |
|---|---|
| `DB_USER=` | `root` (XAMPP-Standard) |
| `DB_PASS=` | leer lassen, falls kein XAMPP-Datenbank-Passwort vergeben wurde |
| `DEFAULT_USER=` | der eigene Name, z.B. `dein_name` — dazu gleich mehr |

**Was hat es mit `DEFAULT_USER` auf sich?** Falls mehrere Personen dasselbe Trading-Journal
nutzen (z.B. eine Familie), bekommt jede Person ihre eigenen Datenbank-Tabellen mit einem
eigenen "Präfix" (einer Art Namens-Kürzel vor jedem Tabellennamen, z.B. `dein_name_trades_raw`).
Welches Präfix zu welchem Namen gehört, steht zentral in einer Datei namens `users.toml`
(liegt schon im `TradingJournal-Weaver`-Ordner) — dort einfach den eigenen Namen eintragen, ohne sich um
das genaue Präfix kümmern zu müssen. Falls der eigene Name dort noch nicht drinsteht: Datei
`users.toml` öffnen und nach demselben Muster wie die vorhandenen Einträge ergänzen, z.B.:
```toml
[dein_name]
prefix = "dein_name_"
```

**Sicherheit:** Die Datei `.env` enthält Zugangsdaten und wird **niemals** mit hochgeladen
(automatisch ausgeschlossen) — das ist so gewollt, nicht anfassen.

---

## 5. Datenbank-Tabellen anlegen

Dieser Befehl legt die eigentlichen Datenbank-Tabellen an, in denen später die Handelsdaten
landen. **Wichtig:** Läuft man ihn ein zweites Mal für dieselbe Kombination, werden
bestehende Daten dort gelöscht und neu angelegt — beim allerersten Setup aber genau richtig.

Den eigenen Namen (aus Schritt 4, mit Unterstrich am Ende) und die gewünschten
Environments einsetzen — mindestens eines ist nötig, z.B. `money` für den Echtgeld-Bereich
oder `test` zum ersten Ausprobieren ohne echtes IBKR-Konto:

```powershell
python -m tools.maintenance.reset_IBKR_DB money dein_name_
```

Für mehrere Environments (z.B. zusätzlich Paper-Trading) den Befehl mit dem jeweils anderen
Environment-Namen wiederholen:

```powershell
python -m tools.maintenance.reset_IBKR_DB paper dein_name_
python -m tools.maintenance.reset_IBKR_DB test dein_name_
```

---

## 6. Automatisierung einrichten

`TradingJournal-Weaver` kann die Datenverarbeitung automatisch für mehrere Personen/Environments auf
einmal erledigen — welche das auf **diesem** Rechner sind, steht in einer Datei namens
`pipeline.toml`, die noch nicht existiert. Aus einer Vorlage anlegen:

```powershell
copy pipeline.toml.example pipeline.toml
```

Jetzt `pipeline.toml` im Text-Editor öffnen und den Platzhalter-Abschnitt anpassen — eigenen
Namen (ohne Unterstrich) und die in Schritt 5 angelegten Environments eintragen:

```toml
[users.dein_name]
environments = ["money"]
```

**Wichtig:** Hier nur Environments eintragen, für die Schritt 5 auch wirklich schon gelaufen
ist — sonst bricht die automatische Verarbeitung später mit einer Fehlermeldung ab, weil die
zugehörigen Tabellen fehlen.

---

## 7. Ersten Testlauf machen

Erst eine "Trockenübung", die nichts wirklich ausführt, nur zeigt was passieren würde:

```powershell
python run_pipeline.py --dry-run
```

Sieht das plausibel aus (die eigenen Environments aus Schritt 6 tauchen auf), ein echter
Testlauf — den eigenen Namen einsetzen:

```powershell
python run_pipeline.py --users dein_name --envs test
```

---

## 8. Praktisch: Schnellzugriff einrichten

Damit man beim nächsten Mal nicht wieder manuell in den Ordner wechseln und die
Arbeitsumgebung (Schritt 2) aktivieren muss, gibt es eine Desktop-Verknüpfung, die beides in
einem Doppelklick erledigt.

Einmalig einrichten — im PowerShell-Fenster, das noch im `TradingJournal-Weaver`-Ordner steht:
```powershell
. .\create-desktop-shortcut.ps1
```

**Falls eine Fehlermeldung mit den Worten "Ausführung von Skripts" oder "deaktiviert"
erscheint:** Windows blockiert auf frisch eingerichteten Rechnern zunächst das Ausführen
von `.ps1`-Dateien. Einmalig beheben — PowerShell **als Administrator** öffnen
(Windows-Taste → `PowerShell` eintippen → Rechtsklick auf den Treffer →
**"Als Administrator ausführen"**) und eintippen:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```
Danach ein normales (nicht als Administrator geöffnetes) PowerShell-Fenster im
`TradingJournal-Weaver`-Ordner öffnen und den Befehl von oben nochmal ausführen.

Danach liegt auf dem Desktop eine Verknüpfung namens **"TradingJournal-Weaver Pipeline"**. Doppelklick
darauf öffnet PowerShell bereits im richtigen Ordner mit aktivierter Arbeitsumgebung — dort
dann direkt z.B. `python run_pipeline.py` eintippen.

---

## Zusammenfassung — künftig starten

Nach der Ersteinrichtung, für den täglichen Gebrauch:

1. Doppelklick auf die Desktop-Verknüpfung "TradingJournal-Weaver Pipeline" (siehe Schritt 8)
2. Darin eintippen: `python run_pipeline.py`

---

## Weiterführende Dokumentation

| Datei | Inhalt |
|---|---|
| [Technisches Handbuch: Installation: TradingJournal-Weaver](../technik/50-installation-weaver.md) | Dieselben Schritte, technischer/kompakter |
| `docs/handbuch/technik/30-befehlsreferenz.md` (im `TradingJournal-Weaver`-Ordner) | Vollständige Befehlsreferenz aller Scripts |
| [TradingJournal-Setup für Einsteiger](50-tradingjournal-installieren.md) | Einrichtung der Weboberfläche (nächster Schritt) |
