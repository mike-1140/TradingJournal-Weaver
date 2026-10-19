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
3. [Konfigurationsdatei anlegen](#3-konfigurationsdatei-anlegen)
4. [Datenbank-Tabellen anlegen](#4-datenbank-tabellen-anlegen)
5. [Automatisierung einrichten](#5-automatisierung-einrichten)
6. [Ersten Testlauf machen](#6-ersten-testlauf-machen)
7. [Praktisch: Schnellzugriff einrichten](#7-praktisch-schnellzugriff-einrichten)

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
gibt es aber eine Abkürzung, siehe Schritt 7.

---

## 3. Konfigurationsdatei anlegen

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
| `DEFAULT_USER=` | der eigene Name, z.B. `anna` — dazu gleich mehr |
| `IMAP_USERNAME=` | das Postfach, an das IBKR die Berichte schickt (Kapitel [IBKR einrichten](20-ibkr-einrichten.md), Abschnitt 4) |
| `IMAP_PASSWORD=` | das Passwort dieses Postfachs |
| `IMAP_SERVER=` | der Posteingangs-Server (IMAP) des Mailanbieters, z.B. `imap.gmx.com` |
| `IBKR_FLEX_QUERIES=` | nur für den Abruf per Web-API: Prüfcode und Query-ID als Paar (Kapitel [IBKR einrichten](20-ibkr-einrichten.md), Abschnitt 5) — sonst leer lassen |

**Was hat es mit `DEFAULT_USER` auf sich?** Falls mehrere Personen dasselbe Trading-Journal
nutzen (z.B. eine Familie), bekommt jede Person ihre eigenen Datenbank-Tabellen mit einem
eigenen "Präfix" (einer Art Namens-Kürzel vor jedem Tabellennamen, z.B. `anna_trades_raw`).
Welches Präfix zu welchem Namen gehört, steht zentral in der Datei `users.toml`. Auch sie wird
aus einer Vorlage angelegt (`copy users.toml.example users.toml`) und dann um die eigenen Namen
ergänzt — Beispiel unten. `DEFAULT_USER` ist der Hauptbenutzer dieses Rechners — sein
Präfix gilt, wenn ein Befehl ohne ausdrückliche Benutzerangabe läuft. Der tägliche automatische
Lauf verarbeitet dagegen alle Benutzer, die in `pipeline.toml` stehen (Schritt 5).

**Welches IBKR-Konto zu wem gehört**, steht in einer dritten Datei, `accounts.toml`. Sie wird
ebenfalls aus einer Vorlage angelegt:

```powershell
copy accounts.toml.example accounts.toml
```

Ohne passenden Eintrag dort überspringt der Import die Berichte eines Kontos (Meldung „Unbekannte
accountId“). Als Schlüssel dienen die **letzten vier Ziffern der IBKR-Kontonummer**.

### Beispiel: Anna und Tom

Anna und Tom nutzen das Journal gemeinsam auf Annas Rechner. Anna hat ein Echtgeld-Konto
(Kontonummer endet auf `1234`) und ein Paper-Konto (`5678`), Tom nur ein Paper-Konto (`9012`).

**Text-Editor, Datei `users.toml`** — beide Namen mit ihrem Präfix:

```toml
[anna]
prefix = "anna_"

[tom]
prefix = "tom_"
```

**Text-Editor, Datei `accounts.toml`** — jedes Konto einem Namen und einem Environment
zuordnen:

```toml
[1234]
user = "anna"
environment = "money"

[5678]
user = "anna"
environment = "paper"

[9012]
user = "tom"
environment = "paper"
```

**Text-Editor, Datei `.env`** — die wichtigen Zeilen (alle anderen bleiben wie in der Vorlage):

```ini
DB_USER=root
DB_PASS=

DEFAULT_USER=anna

IMAP_USERNAME=anna@example.com
IMAP_PASSWORD=Passwort-von-Annas-Postfach
IMAP_SERVER=imap.gmx.com

IBKR_FLEX_QUERIES=PrüfcodeAnna:QueryIdAnnaMoney,PrüfcodeAnna:QueryIdAnnaPaper,PrüfcodeTom:QueryIdTomPaper
```

> [!NOTE]
> `TradingJournal-Weaver` liest **ein** Postfach. IBKR schickt Toms Berichte aber an die
> E-Mail-Adresse seines eigenen IBKR-Kontos — Tom richtet deshalb in seinem Mailprogramm eine
> **Weiterleitung** der IBKR-Mails an Annas Postfach ein (der Absender
> `donotreply@interactivebrokers.com` muss dabei erhalten bleiben). Über die Web-API ist das
> nicht nötig: Dort stehen einfach alle Prüfcode/Query-ID-Paare hintereinander.

Die Präfixe aus `users.toml` werden später auch für die Benutzerkonten der Weboberfläche
gebraucht (Kapitel [TradingJournal installieren](50-tradingjournal-installieren.md)) — dort
muss für Anna `anna_` und für Tom `tom_` stehen.

**Sicherheit:** Die Dateien `.env` und `accounts.toml` enthalten Zugangsdaten bzw. Kontodaten und
werden **niemals** mit hochgeladen (automatisch ausgeschlossen) — das ist so gewollt, nicht
anfassen.

---

## 4. Datenbank-Tabellen anlegen

Dieser Befehl legt die eigentlichen Datenbank-Tabellen an, in denen später die Handelsdaten
landen. **Wichtig:** Läuft man ihn ein zweites Mal für dieselbe Kombination, werden
bestehende Daten dort gelöscht und neu angelegt — beim allerersten Setup aber genau richtig.

Den eigenen Namen (aus Schritt 3, mit Unterstrich am Ende) und die gewünschten
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

**Beispiel Anna und Tom** — Anna braucht Tabellen für *money* und *paper*, Tom nur für *paper*:

```powershell
python -m tools.maintenance.reset_IBKR_DB money anna_
python -m tools.maintenance.reset_IBKR_DB paper anna_
python -m tools.maintenance.reset_IBKR_DB paper tom_
```

---

## 5. Automatisierung einrichten

`TradingJournal-Weaver` kann die Datenverarbeitung automatisch für mehrere Personen/Environments auf
einmal erledigen — welche das auf **diesem** Rechner sind, steht in einer Datei namens
`pipeline.toml`, die noch nicht existiert. Aus einer Vorlage anlegen:

```powershell
copy pipeline.toml.example pipeline.toml
```

Jetzt `pipeline.toml` im Text-Editor öffnen und den Platzhalter-Abschnitt anpassen — eigenen
Namen (ohne Unterstrich) und die in Schritt 4 angelegten Environments eintragen:

```toml
[users.dein_name]
environments = ["money"]
```

**Beispiel Anna und Tom** — genau die Environments aus Schritt 4:

```toml
[users.anna]
environments = ["money", "paper"]

[users.tom]
environments = ["paper"]
```

**Wichtig:** Hier nur Environments eintragen, für die Schritt 4 auch wirklich schon gelaufen
ist — sonst bricht die automatische Verarbeitung später mit einer Fehlermeldung ab, weil die
zugehörigen Tabellen fehlen.

---

## 6. Ersten Testlauf machen

Erst eine "Trockenübung", die nichts wirklich ausführt, nur zeigt was passieren würde:

```powershell
python run_pipeline.py --dry-run
```

Sieht das plausibel aus (die eigenen Environments aus Schritt 5 tauchen auf), ein echter
Testlauf — den eigenen Namen einsetzen:

```powershell
python run_pipeline.py --users dein_name --envs test
```

---

## 7. Praktisch: Schnellzugriff einrichten

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

1. Doppelklick auf die Desktop-Verknüpfung "TradingJournal-Weaver Pipeline" (siehe Schritt 7)
2. Darin eintippen: `python run_pipeline.py`

---

## Weiterführende Dokumentation

| Datei | Inhalt |
|---|---|
| [Technisches Handbuch: Installation: TradingJournal-Weaver](../technik/50-installation-weaver.md) | Dieselben Schritte, technischer/kompakter |
| `docs/handbuch/technik/30-befehlsreferenz.md` (im `TradingJournal-Weaver`-Ordner) | Vollständige Befehlsreferenz aller Scripts |
| [TradingJournal-Setup für Einsteiger](50-tradingjournal-installieren.md) | Einrichtung der Weboberfläche (nächster Schritt) |
