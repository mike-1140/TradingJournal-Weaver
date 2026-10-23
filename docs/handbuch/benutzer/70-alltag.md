# Alltag mit dem TradingJournal

Was im laufenden Betrieb zu tun ist: neue Daten holen und verarbeiten, sie in der App
durchsehen und ergänzen — und was zu tun ist, wenn etwas nicht stimmt. Wie die einzelnen Seiten
der App aussehen, zeigt [Rundgang durch die App](15-rundgang.md); was im Hintergrund genau
passiert, das technische Handbuch ([Architektur und
Import-Pipeline](../technik/10-architektur-und-pipeline.md)).

---

## 1. Daten holen und verarbeiten

**So startest du einen Lauf** — Doppelklick auf die Desktop-Verknüpfung **„TradingJournal-Weaver
Pipeline“** (aus [TradingJournal-Weaver installieren](40-weaver-installieren.md), Schritt 7). Im
PowerShell-Fenster, das sich öffnet:

```powershell
python run_pipeline.py
```

Danach im Browser die App neu laden — die neuen Daten sind da.

**Was dabei passiert** — der Lauf arbeitet sechs Schritte nacheinander ab:

1. **Mails abholen:** neue IBKR-Berichte (Flex Query als XML, Kontoauszug als CSV) aus dem
   Postfach holen; die Mails werden danach gelöscht.
2. **Web-API abfragen:** dieselben Trades auf dem zweiten Weg holen — nur, wenn der Abruf per
   Web-API eingerichtet ist.
3. **Kontostände einlesen:** die Kontoauszüge auswerten (Nettovermögen, Cash, Tagesrendite).
4. **Trades einlesen:** alle neuen Berichte lesen, jedem Benutzer und Environment zuordnen und
   doppelt gelieferte Trades überspringen.
5. **Trades verarbeiten:** offene und geschlossene Positionen bilden, Gewinn/Verlust berechnen,
   Kampagnen fortschreiben.
6. **Sammeldatei ergänzen:** die eingelesenen Berichte zusätzlich in einer Sammeldatei je
   Environment ablegen — daraus lässt sich später alles neu aufbauen (Abschnitt 4).

Welche Benutzer und Environments auf diesem Rechner verarbeitet werden, steht in der
`pipeline.toml` ([TradingJournal-Weaver installieren](40-weaver-installieren.md), Schritt 5). Die
einzelnen Schritte mit ihren technischen Namen und Optionen beschreibt die
[Befehlsreferenz](../technik/30-befehlsreferenz.md). Wer den Lauf automatisch starten lassen
möchte (z. B. täglich per Windows-Aufgabenplanung), findet die Anleitung in [Eigener
Server](75-eigener-server.md), Abschnitt 4 — sie gilt genauso für den eigenen PC.

### Muss das täglich laufen? — Nein, auch einmal im Monat genügt

Die Pipeline muss nicht jeden Tag laufen. Wer nur einmal pro Woche oder einmal im Monat
nachsehen möchte, startet sie einfach dann — es geht nichts verloren:

- **Die Mails warten im Postfach.** IBKR schickt die Berichte weiter jeden Tag, sie bleiben im
  Posteingang liegen, bis der nächste Lauf sie abholt — dann alle auf einmal, Flex Queries wie
  Kontoauszüge. Jeder Tag hat seinen eigenen Kontoauszug, die Kontostände sind also
  lückenlos. Gelesen werden dürfen die Mails, gelöscht oder in einen anderen Ordner
  verschoben nicht (auch nicht durch eine Regel im Mailprogramm); und das Postfach darf nicht
  volllaufen.
- **Das Ergebnis ist dasselbe wie bei täglichen Läufen.** Innerhalb eines Laufs werden alle
  Trades chronologisch verarbeitet, egal aus welcher Mail sie stammen. Auch die
  Kampagnen-Regel „10 Tage ohne Aktivität → CLOSED“ richtet sich nach den Daten der Trades,
  nicht nach dem Tag des Laufs.
- **Der Abruf per Web-API hilft dabei nicht.** Er holt nur den Zeitraum, der in der API-Query
  eingestellt ist (z. B. die letzten 8 Tage), gerechnet ab dem Moment des Abrufs. Bei
  monatlichen Läufen liefert die tägliche Mail die Daten; die Web-API ist nur für Ungeduldige,
  die morgens schon die Vortagesdaten sehen wollen.

Der einzige Nachteil: Das Journal zeigt immer den Stand des letzten Laufs. Dashboard,
Kampagnen und die Liste der noch nicht dokumentierten Trades im Trade Log sind entsprechend
alt.

> [!TIP]
> Wer gar keine tägliche Mail möchte, kann die Flex Query auch einmal im Monat von Hand im
> Kundenportal starten (Zeitraum **Letzter Monat** oder ein benutzerdefinierter Zeitraum) und
> die Datei nach `C:\Trade_XML\incoming_mail` legen — genau wie beim Nachholen alter Daten in
> [TradingJournal-Weaver installieren](40-weaver-installieren.md), Abschnitt 8. Die
> Kontostände fehlen dann allerdings, denn der Kontoauszug kommt nur täglich per Mail.

### Spielt die Reihenfolge der Dateien eine Rolle?

**Innerhalb eines Laufs nicht.** Der Import legt alle Trades aus allen Dateien zuerst in einem
Zwischenspeicher ab. Die Verarbeitung nimmt sie danach streng nach Handelszeitpunkt, egal aus
welcher Datei, welchem Abrufweg (Mail oder Web-API) und in welcher Reihenfolge die Dateien
ankamen. Auch doppelt gelieferte Trades sind kein Problem — sie werden beim Import erkannt und
übersprungen.

**Über mehrere Läufe hinweg schon:** Was einmal verarbeitet ist, wird nicht neu sortiert. Kommen
Trades erst an, **nachdem** jüngere Trades schon verarbeitet wurden, werden sie trotzdem gegen den
aktuellen Stand gebucht. Ein Beispiel:

| Handelstag | Trade | Verarbeitet |
|---|---|---|
| 02.03. | Kauf 100 Aktien | erst im zweiten Lauf (alte Daten, nachgeholt) |
| 10.03. | Verkauf 100 Aktien | im ersten Lauf |

Im ersten Lauf findet der Verkauf keinen Bestand und wird als neue **Short-Position**
eröffnet. Der nachträglich verarbeitete Kauf schließt diese Short-Position dann wieder. Am Ende
ist der Bestand zwar null, aber Richtung, Daten und Kampagne stimmen nicht — aus einer
Long-Position vom 02.03. bis 10.03. ist eine Short-Position geworden, eröffnet am 10.03. und
geschlossen am 02.03.

Im normalen Betrieb passiert das nicht: Jeder Bericht enthält die letzten Tage (siehe
[IBKR einrichten — Flex Queries und Kontoauszug](20-ibkr-einrichten.md), Abschnitt 2), ein Trade
ist also im ersten Bericht nach dem Handelstag enthalten — vor allen jüngeren Trades. Die
Kontostände aus dem Kontoauszug sind ohnehin unabhängig voneinander, dort spielt die Reihenfolge
nie eine Rolle.

Aufpassen muss man nur, wenn **alte Daten nachgeholt** werden: Sie gehören vor den ersten echten
Lauf oder in denselben Lauf (siehe [TradingJournal-Weaver installieren](40-weaver-installieren.md),
Abschnitt 8). Dasselbe gilt sinngemäß, wenn Dateien länger liegen geblieben sind, z. B. weil ein
Konto erst später in `accounts.toml` eingetragen wurde, während für dasselbe Environment schon
neuere Trades verarbeitet waren.

> [!WARNING]
> **Ist es schon passiert, hilft nur ein Neuaufbau des Environments** (`reset_IBKR_DB.py` und
> Import aus der Sammeldatei, siehe Abschnitt 4, „Alles neu aufbauen“). Die Sammeldatei ist nach Datum sortiert und
> enthält auch die nachgeholten Tage, beim Neuaufbau stimmt die Reihenfolge also wieder. Der
> Neuaufbau legt die Tabellen dieses Environments neu an — neben Trades und Kampagnen gehen
> dabei auch die Einträge im **Trade Log** und die **Kontostände** verloren. Die Kontostände lassen sich wiederherstellen, indem die
> verarbeiteten CSV-Dateien aus `C:\Trade_CSV\incoming\<benutzer>\processed` zurück nach
> `C:\Trade_CSV\incoming` kopiert werden; Trade-Log-Einträge vorher sichern (Abschnitt 4,
> „Datenbank sichern und wiederherstellen“).

### So sieht ein Abruf aus

Die beiden Abrufe laufen normalerweise als Teil von `python run_pipeline.py` (Schritte
`fetch_emails` und `fetch_api`), lassen sich aber auch einzeln starten. Die folgenden Protokolle
stammen aus echten Läufen mit vier Konten (Echtgeld, Paper und je ein Konto für automatisierten
Handel). Kontonummern, Query-IDs, Prüfcode-Endungen, Referenznummern und Mailadresse sind ersetzt,
lange Zeilen gekürzt (`…`).

#### Abruf per Web-API

**PowerShell** (im `TradingJournal-Weaver`-Ordner, Arbeitsumgebung aktiv):

```text
(.venv) PS C:\Users\<Benutzer>\Trading\TradingJournal-Weaver> python.exe -m src.get_flexquery_api
================================================================================
---- FlexQueryAPI (2026-10-20 - 07:14:59)
================================================================================
4 Queries konfiguriert | Tokens: ['1111', '2222', '3333', '4444']
[07:14:59] Query 1000001: Anfrage OK nach 1 Versuch(en)/0.8s — HTTP 200, ReferenceCode=1234567890, GetStatement-URL=…
[07:15:00] Query 1000001: Statement erhalten nach 1 Versuch(en)/0.2s — HTTP 200, 1,557 Zeichen
Query 1000001: Erfolgreich nach 1.0s gesamt → C:\Trade_XML\incoming_api\U1234567_20261012_act_money_api_8_0001.xml
Token-Wechsel — warte 30s zur Sicherheit ...
[07:15:30] Query 1000002: Anfrage OK nach 1 Versuch(en)/0.3s — HTTP 200, ReferenceCode=1234567891, GetStatement-URL=…
[07:15:31] Query 1000002: Noch in Verarbeitung/Bereitstellung [1019] (Versuch 1/5, seit 0.3s), warte 10s ...
[07:15:41] Query 1000002: Statement erhalten nach 2 Versuch(en)/10.5s — HTTP 200, 5,035 Zeichen
Query 1000002: Erfolgreich nach 10.7s gesamt → C:\Trade_XML\incoming_api\DU1234567_20261012_act_paper_api_8_0002.xml
Token-Wechsel — warte 30s zur Sicherheit ...
[07:16:11] Query 1000003: Anfrage OK nach 1 Versuch(en)/0.2s — HTTP 200, ReferenceCode=1234567892, GetStatement-URL=…
[07:16:11] Query 1000003: Statement erhalten nach 1 Versuch(en)/0.3s — HTTP 200, 1,563 Zeichen
Query 1000003: Erfolgreich nach 0.5s gesamt → C:\Trade_XML\incoming_api\U7654321_20261012_act_autom_money_api_8_0003.xml
Token-Wechsel — warte 30s zur Sicherheit ...
[07:16:42] Query 1000004: Anfrage OK nach 1 Versuch(en)/0.2s — HTTP 200, ReferenceCode=1234567893, GetStatement-URL=…
[07:16:42] Query 1000004: Statement erhalten nach 1 Versuch(en)/0.2s — HTTP 200, 1,563 Zeichen
Query 1000004: Erfolgreich nach 0.4s gesamt → C:\Trade_XML\incoming_api\DU7654321_20261012_act_autom_paper_api_8_0004.xml
Fertig: 4 neue FlexQuery-Datei(en) gespeichert — Laufzeit gesamt 102.8s
Fertig, Dateien gespeichert: 4
```

So ist das zu lesen:

- **Tokens:** Vom Prüfcode werden nur die letzten vier Zeichen angezeigt. Vier verschiedene
  Prüfcodes bedeuten vier Konten mit je eigenem Kundenportal-Login.
- **Zwei Schritte je Query:** Zuerst die *Anfrage* (IBKR beginnt den Bericht zu erstellen und
  gibt eine Referenznummer zurück), dann das Abholen des fertigen *Statements*.
- **Zwei Versuche beim Paper-Konto sind normal.** Meldung `[1019]` heißt: IBKR stellt den
  Bericht noch bereit. Der Abruf wartet 10 Sekunden und versucht es erneut, höchstens fünfmal.
  Paper-Konten werden bei IBKR offenbar nachrangig bedient und brauchen öfter einen zweiten
  Anlauf.
- **„Token-Wechsel — warte 30s“:** Vor jedem Wechsel auf einen anderen Prüfcode wartet der
  Abruf absichtlich 30 Sekunden. Deshalb dauert der ganze Lauf rund 100 Sekunden, obwohl jede
  einzelne Query in ein bis elf Sekunden fertig ist.
- **Dateiname:** Kontonummer, Datum, Name der Query, letzte vier Ziffern der Query-ID. Das Datum
  ist der **erste** Tag im Bericht — hier der 12.10., weil die Query die letzten 8 Tage abruft.
  Der Teil `_8_` stammt aus dem Namen der Query (`act_money_api_8`) und hat sonst keine
  Bedeutung.

> [!WARNING]
> **Die Web-API höchstens einmal am Tag abrufen.** IBKR geht streng gegen vermeintliche Bots vor:
> Zu viele Anfragen kurz hintereinander — besonders fehlgeschlagene — führen zu einer
> vorübergehenden Sperre (Fehler 1025, siehe [Fehlerbehebung und häufige Fragen](90-fehlerbehebung.md)).
> `TradingJournal-Weaver` schützt sich selbst: Ein zweiter Aufruf am selben Tag fragt IBKR nicht
> erneut, sondern meldet nur `Heute bereits geholt, übersprungen`. Trotzdem nicht mit
> wiederholten Aufrufen herumprobieren — neue Daten gibt es ohnehin erst nach dem nächsten
> Handelstag.

#### Abruf per E-Mail

**PowerShell** (im `TradingJournal-Weaver`-Ordner, Arbeitsumgebung aktiv) — hier nach drei Tagen
ohne Lauf, gekürzt auf den ersten Tag:

```text
(.venv) PS C:\Users\<Benutzer>\Trading\TradingJournal-Weaver> python.exe -m src.get_flexquery_emails
================================================================================
---- FlexQueryEmails (2026-10-20 - 07:31:49)
================================================================================
Mail-Account: trading-mails@example.com
Anhang gespeichert: flex.1000011.paper_30_report.20261007.20261014.xml -> C:\Trade_XML\incoming_mail\flex.1000011.paper_30_report.20261007.20261014.xml
Anhang gespeichert: flex.1000012.money_30_report.20260915.20261014.xml -> C:\Trade_XML\incoming_mail\flex.1000012.money_30_report.20260915.20261014.xml
Anhang gespeichert: flex.1000013.autom_paper_8.20261007.20261014.xml -> C:\Trade_XML\incoming_mail\flex.1000013.autom_paper_8.20261007.20261014.xml
Anhang gespeichert: flex.1000014.autom_money_8.20261007.20261014.xml -> C:\Trade_XML\incoming_mail\flex.1000014.autom_money_8.20261007.20261014.xml
… (dasselbe für den 15. und 16.10.)
Anhang gespeichert: money_act.2000001.20261014.csv -> C:\Trade_CSV\incoming\money_act.2000001.20261014.csv
Activity CSV gespeichert: money_act.2000001.20261014.csv -> incoming/
Anhang gespeichert: autom_money_act.2000002.20261014.csv -> C:\Trade_CSV\incoming\autom_money_act.2000002.20261014.csv
Activity CSV gespeichert: autom_money_act.2000002.20261014.csv -> incoming/
Bereits vorhanden, uebersprungen: autom_money_act.2000002.20261014.csv
Anhang gespeichert: paper_act.2000003.20261014.csv -> C:\Trade_CSV\incoming\paper_act.2000003.20261014.csv
Activity CSV gespeichert: paper_act.2000003.20261014.csv -> incoming/
… (dasselbe für den 15. und 16.10.)
Fertig: 12 FlexQuery-Datei(en), 9 Activity-CSV(s) gespeichert
Fertig, Dateien verarbeitet: 21
```

So ist das zu lesen:

- **Alles auf einmal:** Seit dem letzten Lauf sind drei Tage vergangen, also holt der Abruf die
  Berichte zu drei Handelstagen (14.–16.10.): 4 Flex Queries × 3 Tage = 12 XML-Dateien, dazu
  3 Kontoauszüge × 3 Tage = 9 CSV-Dateien. Die abgeholten Mails werden aus dem Posteingang
  gelöscht.
- **Flex-Query-Dateien** (`.xml`) landen in `C:\Trade_XML\incoming_mail`, **Kontoauszüge**
  (`.csv`) in `C:\Trade_CSV\incoming`.
- **Dateiname der XML:** `flex.<Query-ID>.<Name der Query>.<von>.<bis>.xml`. Der Name sagt
  nichts über den Inhalt: `paper_30_report` enthält hier nur sieben Tage (07.–14.10.) —
  maßgeblich sind die beiden Datumsangaben, nicht die Zahl im Namen.
- **„Bereits vorhanden, uebersprungen“:** Derselbe Kontoauszug kam ein zweites Mal an und wird
  nicht doppelt gespeichert — harmlos.
- **Nur drei Kontoauszüge für vier Konten:** Für das vierte Konto ist kein Kontoauszug
  eingerichtet. Das ist erlaubt, er ist optional (siehe [IBKR einrichten — Flex Queries und
  Kontoauszug](20-ibkr-einrichten.md), Abschnitt 6).

## 2. Nach dem Import: ein typischer Durchgang

Die Daten sind nur die eine Hälfte eines Journals — die andere ist, was du dazu festhältst. Ein
Durchgang nach dem Import, z. B. am Morgen mit den Daten vom Vortag:

1. **Dashboard** — wie steht es insgesamt? Kennzahlen, Kontostand und P&L-Verlauf für das
   gewählte Environment ([Rundgang durch die App](15-rundgang.md), Abschnitt 2).
2. **Analyse → Aktivität** — was ist seit dem letzten Mal passiert? Alle Buchungen über alle
   Symbole, wochenweise, ohne jede Kampagne einzeln öffnen zu müssen.
3. **Kampagnen und Spreads** — bei Bedarf einzelne Positionen genauer ansehen: Verlauf,
   Buchungen, Ergebnis je Spread (Rundgang, Abschnitte 5 und 6).
4. **Log** — neue Trades dokumentieren. Die Zahl neben *Log* im Menü zeigt, wie viele Kampagnen
   der letzten 30 Tage noch keinen Eintrag haben; **Dokumentieren** öffnet ein vorausgefülltes
   Formular. Am wertvollsten ist der Eintrag **vor** dem Trade: Plan, Begründung und
   Ausstiegsszenario, solange sie frisch sind. Nach dem Schließen trägst du Ergebnis und Notizen
   nach — so stehen Plan und Ausgang nebeneinander (Rundgang, Abschnitt 7).
5. **Psychologie** — wie kam der Trade zustande? Stimmung, Motivation, Einhaltung der eigenen
   Regeln, Versuchungen und die Lektion. Die Regelwerke dafür legst du einmal an; die
   Auswertung zeigt mit der Zeit, welche Muster Geld kosten (Rundgang, Abschnitt 8).

Log und Psychologie ergänzen sich: Das **Log** hält Plan und Ergebnis **je Trade** fest, die
**Psychologie** misst über die Zeit, wie diszipliniert du deinen Regeln folgst.

> [!TIP]
> Für den schnellen Eintrag zwischendurch gibt es oben in jeder Seite den gelben Knopf
> **Neuer Eintrag** ([Rundgang durch die App](15-rundgang.md), Abschnitt 1).

## 3. Kampagnen: offen, wartend, geschlossen

Wie Kampagnen entstehen und enden, beschreibt [Überblick — vom Trade bis zur
Auswertung](10-ueberblick.md), Abschnitt 4.2. Im Alltag heißt das:

- **Aktiv** — es ist noch etwas offen (Aktien oder Optionen).
- **Pending** — alles ist geschlossen, die Kampagne wartet aber noch 10 Tage. Ein neuer Trade
  im selben Symbol (z. B. der nächste Put einer Wheel-Strategie oder ein Roll) setzt **dieselbe**
  Kampagne fort.
- **Geschlossen** — 10 Tage ohne neuen Trade. Der nächste Trade in diesem Symbol beginnt eine
  neue Kampagne.

Eine Kampagne kann also ein paar Tage *Pending* stehen, obwohl die Position längst zu ist — das
ist gewollt. Die 10 Tage sind Kalendertage und zählen ab dem Datum des letzten Trades, nicht
ab dem Tag, an dem der Import lief (siehe Abschnitt 1, „Muss das täglich laufen?“).

> [!TIP]
> Die Frist lässt sich ändern — in der `.env` von `TradingJournal-Weaver`, z. B.
> `MAX_GAP_DAYS=14` (sinnvoll sind etwa 7 bis 14 Tage). Sie gilt dann für alle künftig
> verarbeiteten Trades. Bereits geschlossene Kampagnen ändern sich dadurch nicht; wer die neue
> Frist auch für die Vergangenheit möchte, baut das Environment neu auf (Abschnitt 4).

## 4. Wenn etwas nicht stimmt

Alle Befehle laufen im PowerShell-Fenster der Desktop-Verknüpfung (Ordner
`TradingJournal-Weaver`, Arbeitsumgebung aktiv). Viele Fehlerbilder samt Lösung sammelt außerdem
[Fehlerbehebung und häufige Fragen](90-fehlerbehebung.md).

### Eine XML-Datei gefahrlos ausprobieren

Für eine fragliche oder fremde Flex-Query-Datei gibt es das Environment **TEST** — es berührt
die echten Daten nicht.

1. **[Windows-Explorer]** Die Datei so benennen, dass sie mit `flex.` beginnt und auf `.xml`
   endet (z. B. `flex.probe.xml`), und in den Ordner `C:\Trade_XML\test\<benutzer>\incoming\`
   legen — `<name>` wie im `[[test]]`-Block der `pipeline.toml`.
2. **[PowerShell]** Ganz normal laufen lassen:

   ```powershell
   python run_pipeline.py
   ```

3. In der App oben auf **TEST** umschalten und das Ergebnis ansehen.

Die Datei wird unabhängig von ihrer Kontonummer immer in TEST eingelesen.

### Eine Position bleibt offen, obwohl sie geschlossen ist

Kommt eine Eröffnung an, die passende Schließung aber nie (z. B. wegen einer Datenlücke), bleibt
die Position offen stehen. **[PowerShell]** Erst ansehen, was entfernt würde — ohne `--execute`
wird nichts gelöscht (Environment, eigenes Präfix und Symbol einsetzen):

```powershell
python -m tools.maintenance.cleanup_stale_positions money --prefix anna_ --symbols XYZ
```

Stimmt die Anzeige, denselben Befehl mit `--execute` am Ende wiederholen. Statt `--symbols`
geht auch `--older-than 2026-01-01` (alles vor diesem Datum).

### Datenbank sichern und wiederherstellen

Das Skript `db-backup.ps1` sichert **alle** Datenbanken auf einmal: die fünf Environments (mit
Trades, Kampagnen, Kontoständen, Trade Log und Psychologie) und die Datenbank der Weboberfläche
(Benutzerkonten). Es liest die Zugangsdaten aus der `.env` von TradingJournal-Weaver; MySQL muss
laufen.

**Sichern — [PowerShell]** im Ordner `TradingJournal-Weaver`:

```powershell
.\db-backup.ps1
```

Die Sicherungen landen in `TradingJournal-Weaver\database\db\`, je Datenbank eine Datei
`<datenbank>_backup_JJJJMMTT_HHMM.sql`. Mit `-UsbLabel "NAME"` wird zusätzlich auf das
USB-Laufwerk mit diesem Namen kopiert (der Name, der im Explorer beim Laufwerk steht).

**Wiederherstellen — [PowerShell]** im selben Ordner, zuerst als Trockenlauf:

```powershell
.\db-backup.ps1 -Restore -DryRun
.\db-backup.ps1 -Restore
```

Der Trockenlauf zeigt nur, welche Sicherung je Datenbank eingespielt würde — immer die neueste.
Ohne `-DryRun` fragt das Skript für jede Datenbank einzeln nach. Bevor es eine Datenbank
überschreibt, sichert es deren aktuellen Stand zusätzlich als
`<datenbank>_prerestore_JJJJMMTT_HHMMSS.sql` — ein versehentliches Wiederherstellen lässt sich
so rückgängig machen.

> [!CAUTION]
> Die Sicherungen enthalten alle Handelsdaten. Nicht weitergeben und nicht in Foren oder auf
> GitHub hochladen.

### Alles neu aufbauen

Wenn die Daten eines Environments durcheinander sind — etwa weil Trades in falscher Reihenfolge
ankamen (Abschnitt 1, „Spielt die Reihenfolge der Dateien eine Rolle?“) —, lässt es sich aus der
Sammeldatei komplett neu aufbauen.

> [!WARNING]
> Der Neuaufbau legt die Tabellen des Environments neu an. Dabei gehen auch die Einträge im
> **Log** und die **Kontostände** verloren. Psychologie-Einträge bleiben erhalten. Vorher die
> Datenbank sichern (siehe „Datenbank sichern und wiederherstellen“ oben).

**[PowerShell]** Beispiel für Annas Echtgeld-Bereich:

```powershell
python -m tools.maintenance.reset_IBKR_DB money anna_
python run_pipeline.py --steps import --from-summary --users anna --envs money
python run_pipeline.py --steps process --users anna --envs money
```

**[Windows-Explorer]** Die Kontostände kommen zurück, indem die verarbeiteten CSV-Dateien aus
`C:\Trade_CSV\incoming\<benutzer>\processed` wieder nach `C:\Trade_CSV\incoming` kopiert werden;
der nächste normale Lauf liest sie ein.

## 5. Mehrere Benutzer

Jede Person hat eigene Daten (eigenes Präfix, eigene IBKR-Konten in `accounts.toml`). Wie man auf
dem eigenen PC zwischen den Benutzern wechselt und wie es auf einem Server aussieht, beschreibt
[Erster Start — UI-Erstkonfiguration](60-erster-start.md), Abschnitt 3.
