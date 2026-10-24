# Beispiele gesucht — Sonderfälle, die ich selbst nicht prüfen konnte

Das TradingJournal verarbeitet die Berichte, die Interactive Brokers (IBKR) als **Flex Query**
(XML) liefert. Geprüft ist alles, was in meinen eigenen Konten bisher vorgekommen ist. Einige
Ereignisse sind dort aber **noch nie aufgetreten** — für sie weiß ich weder sicher, wie IBKR sie in
der XML-Datei darstellt, noch, ob das Journal sie richtig verarbeitet.

Hier hilft die Gemeinschaft: Wer einen dieser Fälle schon einmal im eigenen Konto hatte, kann mit
einer Beschreibung oder — noch besser — mit der **anonymisierten XML-Datei des betreffenden Tages**
viel bewirken. Schon eine Antwort auf eine einzelne Frage unten hilft.

> [!CAUTION]
> Flex-Query-Dateien enthalten vollständige Handelsdaten. **Vor dem Teilen die Kontonummer
> überall ersetzen** (z. B. durch `U1234567`, bei Paper-Konten `DU1234567`) — sie steht im Kopf
> jedes Tagesberichts und an jedem Trade. Trade-IDs, Kurse und Mengen bitte lassen, sonst ist der
> Fall nicht nachvollziehbar. Die genaue Anleitung steht im technischen Handbuch,
> [Bekannte Grenzen und offene Fragen](docs/handbuch/technik/90-bekannte-grenzen.md), Abschnitt
> „Mithelfen“.

**Wohin?** Für den Anfang bitte ins Forum, in dem das TradingJournal vorgestellt wurde. Später
laufen solche Beispiele als Issue im Repository
[TradingJournal-Weaver](https://github.com/mike-1140/TradingJournal-Weaver).

---

## Übersicht

| Nr. | Fall | Bisher gesehen | Dringlichkeit |
|---|---|---|---|
| 1 | Aktiensplit während einer offenen Option oder eines Spreads | einmal, ohne offene Position | **hoch** — verfälscht Positionen |
| 2 | Forward Split und `SS`-Split bei Aktien | nur Reverse Splits | mittel |
| 3 | Teil-Zuteilung (z. B. 1 von 2 Kontrakten) | nie | mittel |
| 4 | Vorzeitige Zuteilung des verkauften Beins eines Spreads | nie | mittel |
| 5 | Ausübung eigener Optionen mit Aktienlieferung | nie | mittel |
| 6 | Fusion, Spin-off, Symbolwechsel, Delisting | nie | **hoch** — verfälscht Positionen |
| 7 | Rolls und schließende Combo-Orders: Feld `openCloseIndicator` | ja, aber Feld ungeprüft | mittel |
| 8 | Futures und Optionen auf Futures | nie | niedrig |
| 9 | Konto mit anderer Basiswährung als EUR | nie | niedrig |

---

## 1. Aktiensplit während einer offenen Option oder eines Spreads

**Worum es geht:** Bei einem Split passt die Börse laufende Optionen an — je nach Verhältnis
ändern sich Anzahl, Ausübungspreis, Multiplikator oder Symbol des Kontrakts (bei krummen
Verhältnissen entstehen oft „angepasste“ Kontrakte mit Sondersymbol wie `XYZ1`). Das Journal
erkennt den Split, stellt aber **offene Options-Positionen nicht auf den neuen Kontrakt um**. Ein
späterer Verfall oder Rückkauf unter dem neuen Kontrakt würde dann eine falsche Gegenposition
eröffnen.

**Bisher gesehen** — der einzige Fall: TQQQ, Forward Split 2:1 am 20.11.2025 (Paper-Konto). Im
Abschnitt *Kapitalmaßnahmen* standen genau zwei Options-Zeilen mit derselben `actionID`:

```xml
<CorporateAction type="FS" actionID="160563833" reportDate="20/11/2025" assetCategory="OPT"
  symbol="TQQQ 251219P00037500" quantity="1"  multiplier="100" underlyingSymbol="TQQQ"
  description="TQQQ(US74347X8314) SPLIT 2 FOR 1 (TQQQ 251219P00037500, TQQQ 19DEC25 37.5 P, )" />
<CorporateAction type="FS" actionID="160563833" reportDate="20/11/2025" assetCategory="OPT"
  symbol="TQQQ 251219P00042500" quantity="-1" multiplier="100" underlyingSymbol="TQQQ"
  description="TQQQ(US74347X8314) SPLIT 2 FOR 1 (TQQQ 251219P00042500, TQQQ 19DEC25 42.5 P, )" />
```

Das passt nicht zum erwarteten Bild „alter Kontrakt raus, neuer Kontrakt rein“: Es sind zwei
**verschiedene** Ausübungspreise (37,5 und 42,5) mit Menge +1 und −1, und kein Kontrakt mit
halbiertem Ausübungspreis oder doppelter Anzahl. Ob das die beiden Beine eines Spreads waren, ob
die angepassten Kontrakte an einem anderen Tag oder in einem anderen Abschnitt kamen, ist offen.

**Fragen:**

1. Welche Zeilen liefert IBKR im Abschnitt *Kapitalmaßnahmen* für eine **offene Option** bei einem
   Split — eine Zeile für den alten und eine für den neuen Kontrakt, oder anders?
2. Wie sieht der **neue Kontrakt** aus: halbierter Ausübungspreis und doppelte Anzahl, gleicher
   Ausübungspreis mit geändertem Multiplikator, oder ein Sondersymbol (z. B. `TQQQ1`)?
3. Bei einem **Spread** (mehrere Beine): eine Zeile je Bein, alle mit derselben `actionID`?
4. Wie meldet IBKR später den **Verfall, die Zuteilung oder den Rückkauf** des angepassten
   Kontrakts — unter welchem Symbol und mit welcher Menge?

**Was hilft:** die XML-Datei des Split-Tags und die des späteren Verfalls bzw. Rückkaufs, dazu
kurz die Position vor dem Split (z. B. „Bull Put Spread 42,5/37,5, 1 Kontrakt“).

---

## 2. Forward Split und `SS`-Split bei Aktien

**Worum es geht:** Geprüft sind nur **Reverse Splits** (Zusammenlegung, Typ `RS`). Für sie liefert
IBKR ein Paar mit derselben `actionID`: die alten Aktien mit negativer Menge und Symbol-Endung
`.OLD`, die neuen mit positiver Menge. Das Journal rechnet für die Typen `RS`, `FS` (Forward Split)
und `SS` gleich: Faktor = neue Menge ÷ alte Menge.

**Bisher gesehen** (Reverse Split 1:50):

```xml
<CorporateAction type="RS" actionID="150790904" assetCategory="STK" symbol="APDN"     quantity="30" ... />
<CorporateAction type="RS" actionID="150790904" assetCategory="STK" symbol="APDN.OLD" quantity="-1500" ... />
```

**Fragen:**

1. Liefert IBKR bei einem **Forward Split** (z. B. 2:1, 4:1) dasselbe Paar aus `.OLD`- und neuer
   Zeile?
2. Was bedeutet der Typ **`SS`** genau, und wie sieht er in der XML aus?
3. Was passiert mit **Bruchteilen** (z. B. 3:2-Split bei ungerader Stückzahl): eigene Zeile mit
   Barausgleich?

**Was hilft:** die XML-Datei des Split-Tags.

---

## 3. Teil-Zuteilung

**Worum es geht:** Bei einer Zuteilung (Assignment) verbindet das Journal die Option mit dem
gelieferten Aktien-Trade. Ist nur **ein Teil** einer Position betroffen (z. B. 1 von 2 verkauften
Puts), steht nach heutigem Code-Stand *Closed* statt *Assigned* im abgeschlossenen Trade.

**Fragen:**

1. Wie meldet IBKR eine Teil-Zuteilung: ein Eintrag im Abschnitt *Optionsausübungen,
   -zuteilungen und -fälligkeiten* mit der Teilmenge, und die restlichen Kontrakte verfallen oder
   bleiben offen in einem eigenen Eintrag?
2. Kommt der Aktien-Trade als eigene Zeile mit derselben Menge × Multiplikator?

**Was hilft:** die XML-Datei des Zuteilungstags.

---

## 4. Vorzeitige Zuteilung des verkauften Beins eines Spreads

**Worum es geht:** Bei einem Credit-Spread kann das verkaufte Bein **vor dem Verfall** zugeteilt
werden (bei Calls oft vor einem Dividendentermin). Dann liegen plötzlich Aktien im Depot, während
das gekaufte Bein noch läuft. Zuteilungen am Verfallstag sind geprüft, vorzeitige nicht.

**Fragen:**

1. Unterscheidet sich die Darstellung in der XML von einer Zuteilung am Verfallstag?
2. Was zeigt das Journal danach in der Spreads-Ansicht und in der Kampagne — ist der Spread noch
   offen, und wird das verbliebene Bein richtig weitergeführt?

**Was hilft:** die XML-Datei des Zuteilungstags und die der späteren Glattstellung.

---

## 5. Ausübung eigener Optionen mit Aktienlieferung

**Worum es geht:** Wer eine **gekaufte** Option selbst ausübt (Exercise), bekommt bzw. liefert
Aktien. Wie das Journal diese Aktien einbucht, ist nur aus dem Code abgeleitet; die Verknüpfung
zwischen Option und Aktien-Trade fehlt dabei heute (siehe [Roadmap](ROADMAP.md)).

**Fragen:**

1. Steht im Abschnitt *Optionsausübungen* der Typ `Exercise`, und kommt der Aktien-Trade als
   eigene Zeile mit Hinweis auf die Ausübung?
2. Gibt es Unterschiede zwischen ausgeübten **Calls** (Aktien kommen) und **Puts** (Aktien gehen)?

**Was hilft:** die XML-Datei des Ausübungstags.

---

## 6. Fusion, Spin-off, Symbolwechsel, Delisting

**Worum es geht:** Außer Splits behandelt das Journal keine Kapitalmaßnahmen eigens. Eine Fusion,
ein Spin-off oder ein Symbolwechsel würde heute wie ein normaler Trade zum Preis 0 verarbeitet —
Positionen und Ergebnis wären danach falsch.

**Fragen:**

1. Welcher **Typ** (`type`) steht in der XML für Fusion, Spin-off, Symbolwechsel,
   Barabfindung und Delisting?
2. Kommen die Zeilen ebenfalls als Paar (alt raus, neu rein) mit derselben `actionID`?
3. Bei einem **Spin-off**: Wie wird der Einstandspreis zwischen alter und neuer Aktie aufgeteilt —
   steht das in der XML?
4. Was passiert mit **Optionen** auf die betroffene Aktie?

**Was hilft:** die XML-Datei des Ereignistags. Auch eine reine Beschreibung („Fusion von A und B,
1 A-Aktie wurde zu 0,8 B-Aktien“) mit dem `type` aus der XML hilft schon.

---

## 7. Rolls und schließende Combo-Orders: das Feld `openCloseIndicator`

**Worum es geht:** Ein Roll als Combo-Order (alte Option zurückkaufen, neue verkaufen) wird heute
als Calendar- oder Diagonal-Spread erkannt, und das Zurückkaufen eines Spreads per Combo erscheint
als „umgekehrter“ Spread. Abhilfe wäre, Beine, die eine bestehende Position **schließen**, vor der
Erkennung herauszufiltern. Dafür gibt es in der XML das Feld `openCloseIndicator` (`O` = eröffnend,
`C` = schließend).

**Frage:** Füllt IBKR `openCloseIndicator` bei **allen Beinen** einer Combo-Order zuverlässig —
auch bei Rolls, bei denen ein Bein schließt und eines eröffnet? Gibt es Fälle mit leerem Feld oder
`C;O`?

**Was hilft:** die XML-Datei eines Tages mit einem Roll per Combo-Order.

---

## 8. Futures und Optionen auf Futures

**Worum es geht:** Der Import ist für Aktien, Aktien- und Indexoptionen sowie Devisentausch gebaut
und mit solchen Daten geprüft. Futures (`FUT`) und Optionen auf Futures (`FOP`) kamen nie vor.

**Frage:** Wer Futures handelt: Läuft der Import durch, und stimmen Positionen und Ergebnis? Wenn
nicht — welche Fehlermeldung erscheint im Protokoll?

**Was hilft:** eine XML-Datei mit einem Future-Trade (Eröffnung und Schließung).

---

## 9. Konto mit anderer Basiswährung als EUR

**Worum es geht:** Alle Umrechnungen sind mit **EUR als Basiswährung** geprüft (Beträge in
Handelswährung, zusätzlich in EUR über den Wechselkurs `fxRateToBase`, den IBKR je Trade liefert).
Bei einem Konto in USD, CHF oder GBP sind die Werte zwar ebenfalls vorhanden, aber nicht geprüft —
und Spalten wie „EUR“ wären dann falsch beschriftet.

**Frage:** Wer ein Konto mit anderer Basiswährung hat: Zeigt das Journal plausible Werte, und
welche Stellen sind irreführend beschriftet?

**Was hilft:** eine Beschreibung mit Screenshot (Beträge dürfen geschwärzt sein).
