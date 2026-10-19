# TradingJournal

TradingJournal ist mein selbstgehostetes Journal für den Options- und Aktienhandel über Interactive Brokers — es importiert meine IBKR-Trades automatisch, fasst sie zu durchgehenden Kampagnen und Spreads zusammen und macht Bestand, P&L und Kennzahlen auf einen Blick sichtbar. Der Schwerpunkt liegt auf allem, was generische Journal-Tools nicht abbilden: Options-Rollen, Spread-Strukturen, Zuteilungen aus Optionen in Aktienpositionen — ergänzt um ein Psychologie-Modul, das Ergebnis und Entscheidungsqualität bewusst trennt. Besonders ist, dass alles komplett lokal läuft, ohne Cloud-Zwang und ohne Abo. Die Idee dafür ist über ein Jahr alt, die aktuelle Version ist aus meinen eigenen Bedürfnissen gewachsen. Jetzt wage ich den nächsten Schritt und mache den Quellcode öffentlich (PolyForm Noncommercial).

> [!IMPORTANT]
> **Läuft nur unter Windows.** Die gesamte Installation ist auf Windows zugeschnitten: die
> Schritt-für-Schritt-Anleitungen, die Hilfsskripte (PowerShell) und die Ablageordner für die
> IBKR-Berichte (`C:\Trade_XML\`, `C:\Trade_CSV\`), die im Code fest vorgegeben sind. Andere
> Betriebssysteme unterstütze ich derzeit nicht.

## Ausprobieren ohne Installation

Wer sich das TradingJournal erst einmal ansehen möchte, kann die öffentliche Demo nutzen — mit
erfundenen Beispieldaten, ganz ohne eigene Installation:

- **Adresse:** <https://204-168-201-48.sslip.io/login>
- **E-Mail:** `demo@example.com`
- **Passwort:** `Demo-Trading2026!`

Änderungen in der Demo werden nicht gespeichert. Die Demo ist ein freiwilliges Angebot und
kann zeitweise nicht erreichbar sein.

## Die Eckpunkte

- **Komplett lokal, volle Datenhoheit.** Ich nutze keinen Cloud-Dienst und keinen Drittanbieter-Server. Die App läuft auf meiner eigenen Maschine (lokaler PC oder ein eigener Server, falls vorhanden), meine Kontodaten bleiben dort.
- **Quellcode offen, Nutzung kostenlos — aber nicht kommerziell.** Ich habe beide Repositories öffentlich gemacht: [TradingJournal](https://github.com/mike-1140/TradingJournal) (die Weboberfläche) und [TradingJournal-Weaver](https://github.com/mike-1140/TradingJournal-Weaver) (Import und Datenverarbeitung). Jeder darf das Journal für die eigenen Konten nutzen (auch Echtgeld), den Code lesen, anpassen und kostenlos weitergeben. Verkaufen, als bezahlten Dienst anbieten oder in ein kommerzielles Produkt einbauen ist nicht erlaubt (PolyForm-Noncommercial-Lizenz, Details im README).
- **Zugeschnitten auf Interactive Brokers.** Ich importiere über IBKR FlexQuery — andere Broker unterstütze ich aktuell nicht.
- **Kein Echtzeit-Tool.** Mein Import läuft mit ein bis zwei Tagen Nachlauf zum echten Handelstag. Für mich ist das Journal deshalb eher Dokumentation und Analyse im Rückblick als ein aktives Trading-Tool für den laufenden Tag.
- **5 getrennte Umgebungen.** MONEY, PAPER, TEST, AUTOM_MONEY und AUTOM_PAPER halten Echtgeld, Papertrading, Testdaten und automatisierten Handel sauber auseinander.
- **Automatische USD/EUR-Umrechnung.** Ich sehe meinen P&L in beiden Währungen, ohne selbst nachzurechnen. Reine Währungsumtausch-Trades (USD↔EUR-Wechsel) haben dafür eine eigene Übersicht, inklusive Zusammenfassung, wenn IBKR eine Order in mehreren Teilausführungen gefüllt hat.
- **Konfigurierbares Dashboard.** Ich blende Kacheln per Toggle-Modal ein und aus, wie ich sie gerade brauche.
- **Dokumentiert für den Einstieg.** Ich habe Setup-Anleitungen für Windows/MySQL/Laravel/Python geschrieben, dazu jetzt ein eingebautes Handbuch direkt in der App, das jeden Menüpunkt erklärt.
- **Hobbyprojekt, best effort.** Ich biete keinen Servicevertrag (z.B. wie schnell ich bei einer Fehlermeldung erste Schritte einleite) und auch kein Support-Team — nur mich, in meiner Freizeit. Das steht auch im README.
- **KI-unterstützt entwickelt.** Das Projekt wurde mit Claude von Anthropic umgesetzt.

## Wie mein Workflow aussieht

1. **Import der Daten von IBKR** — eine FlexQuery liefert mir die Rohdaten meines Kontos als XML (durch Zustellung per Mail und/oder Abfrage per API)
2. **Import & Verarbeitung (Python)** — ich parse die Rohdaten (XML-Dateien), führe sie zu Kampagnen und Spreads zusammen und berechne laufenden Bestand und P&L.
3. **Ansehen & Verstehen (Laravel-UI)** — im Dashboard, bei Kampagnen, Spreads und in den Symbol-/Zeitraum-Auswertungen sehe ich, wie sich mein Portfolio entwickelt.
4. **Reflektieren** — im Entscheidungsjournal halte ich fest, warum ich einen Trade eingegangen bin, im Psychologie-Modul, ob ich mich an meine eigenen Regeln gehalten habe.

Den Import kann ich jederzeit von Hand anstoßen (ein einziger Befehl) oder automatisch laufen lassen, etwa täglich über die Windows-Aufgabenplanung. Weil IBKR die Berichte erst nach Handelsschluss erstellt, sehe ich meine Trades mit dem erwähnten Nachlauf von ein bis zwei Tagen. Die App ist für mich deshalb Auswertung und Journal-Pflege — kein Live-Cockpit für den Handelstag selbst.

## Pro & Contra

**Dafür spricht:**

- Ich habe volle Kontrolle über meine eigenen Finanzdaten, nichts verlässt meine eigene Maschine
- Ich muss nichts mehr händisch nachtragen — die IBKR-Daten fließen automatisiert ein
- Ich bilde Options-Spezifika ab, die generische Journal-Tools nicht können: Kampagnen mit Rollen, Spread-Strukturen, Zuteilungen aus Optionen in Aktienpositionen
- Ich trenne Ergebnis und Entscheidungsqualität durch das Psychologie-Modul 
- Kostenlos und quelloffen, keine Abo-Falle
- Den Code habe ich nach bestem Wissen und Gewissen erstellt und geprüft

**Dagegen spricht:**

- Ich unterstütze nur Interactive Brokers als Datenquelle — für andere Broker ist es aktuell unbrauchbar
- Kein Echtzeit-Tool: Ich sehe meine Positionen mit ein bis zwei Tagen Nachlauf, nicht live. 
- Mein Setup ist kein Einzeiler: Windows, MySQL, PHP/Laravel, Python und mehrere Konfigurationsdateien müssen zusammenspielen. Wer sich vor der Kommandozeile scheut, wird hier nicht glücklich
- Ich habe nur begrenzte Testabdeckung — solide Kernlogik, aber keine durchgängige, produktionsreife QA
- Ich biete keinen Support und keine Roadmap-Garantie — ich baue weiter, wenn ich Zeit und Lust habe
- Reine Web-Oberfläche für meinen Schreibtisch, keine mobile App

## Persönliche Entwicklung

- Angefangen habe ich vor über einem Jahr. Die Dokumentation meiner Trades durch die Eingabe in Excel-Sheets war mir immer zu mühsam. Dokumentation auf Papier noch mehr. Dann bin ich auf die Idee gekommen mir die Daten von IBKR zu holen (IBKR hat meine Trades ohnehin als strukturierte Datensätze - FlexQuery). Damit habe ich meine ersten Versuche mit Python, einer MySQL-Datenbank und Google Sheets als Darstellungstool gestartet. 
  Das hat eine Weile gut funktioniert — bis ich angefangen habe, verstärkt mit Optionen zu handeln. Da ich vor allem Spreads handle, wegen der Margin-Vorteile, wurde die Darstellung/Dokumentation in einer Tabelle immer umständlicher. Außerdem wollte ich eine verfolgbare Dokumentation der Wheel-Strategie (Bonus-Strategie), was mit Googlesheets nicht möglich war.
  Über ein anderes Projekt bin ich auf Laravel gestoßen und habe beschlossen, mir damit eine echte Oberfläche zu bauen, statt weiter gegen Tabellenkalkulationen zu kämpfen — so ist die nächste Version des TradingJournal entstanden.

- Die Kampagnen, also die durchgehende Geschichte aller Trades zu einem Symbol statt einer losen Liste von Einzeltrades, waren dabei ursprünglich als reine Dokumentation für mein Wheel-Trading (Bonus-Strategie) gedacht und sind von dort aus gewachsen. 

- Weiters war es mir immer wichtig: kein Geld für Tools und/oder Abos ausgeben. Die verschiedenen Tools (im Internet) sind sehr mächtig und können oft viel mehr als mein Tradingjournal, doch alles läuft Online und meine Daten stehen IRGENDWO ... 
  Kontoauszüge sind Finanzdaten — die wollte ich ohnehin nicht auf einen fremden Host hochladen, sondern in meiner eigenen, lokalen Umgebung behalten.

- Dazu kam ein weiterer Punkt, der mir beim eigenen Handeln immer wieder auffiel: Das Ergebnis eines Trades sagt mir nichts darüber, ob die Entscheidung dahinter gut war. Ein Gewinn aus Disziplin und ein Gewinn aus einem Impuls sehen in meinem P&L identisch aus. Also habe ich neben der reinen Buchhaltung ein Modul gebaut, das genau das für mich trennt.  
  Das Buch von Annie Duke - Thinking in Bets - hat mich dazu inspiriert: Entscheidungsqualität ≠ Ergebnisqualität. Ein schlechter Trade kann durch Glück Geld verdienen — eine gute Entscheidung kann durch Pech Geld verlieren. Langfristig zählt nur der Prozess.

- Und ein technischer Punkt: Ich programmiere gerne und bringe das Grundwissen mit, aber erst über den KI-Boom und Vibe-Coding bin ich so tief in Laravel eingestiegen (ich habe das Projekt mit Claude von Anthropic umgesetzt). Ohne das wäre ich heute weit davon entfernt, eine funktionierende Oberfläche zu haben. 

## Status

Das TradingJournal ist im täglichen Einsatz und wird laufend weiterentwickelt. Mit der Veröffentlichung des Quellcodes wünsche ich mir Rückmeldungen aus der Praxis — gerade auch zu Lücken in der Dokumentation. Fragen, Fehlermeldungen und Ideen gerne als Issue im GitHub-Repository melden.
