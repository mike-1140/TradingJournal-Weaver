# Bekannte Grenzen und offene Fragen

Dieses Kapitel sammelt ehrlich, was `TradingJournal-Weaver` und TradingJournal **nicht** oder
**noch nicht sicher** können. Es hat drei Teile:

1. **Bekannte Grenzen** — im Code nachgewiesen, teils auch in echten Daten beobachtet.
2. **Ungetestet — Beispiele gesucht** — Fälle, für die der Code vermutlich passt, für die aber
   keine echten Daten vorliegen.
3. **Mithelfen** — wie du mit einem eigenen Beispiel helfen kannst.

Jeder Eintrag verweist auf die Stelle im Handbuch, an der der Ablauf ausführlich beschrieben ist.
Wird eine Grenze behoben, verschwindet sie aus diesem Kapitel.

> [!NOTE]
> Geprüft gegen den Code und gegen die echten Daten des Autors
> (mehrere Echtgeld- und Paper-Konten). „Schon vorgekommen“ bezieht sich auf diese Daten.

---

## 1. Bekannte Grenzen

### 1.1 Import und Verarbeitung

#### Andere Kapitalmaßnahmen werden nicht eigens behandelt

Nur Splits (`RS`, `FS`, `SS`) haben eine eigene Logik. Fusionen, Spin-offs, Symbolwechsel usw.
würden wie normale Trades zum Preis 0 verarbeitet und Positionen sowie Gewinn/Verlust verfälschen.
*Schon vorgekommen:* nein. *Details:* [Architektur und Import-Pipeline](10-architektur-und-pipeline.md),
§ 6.2 „Fall SPLIT“.

#### Kein Forex-Trading

Devisentausch wird nur als Umtausch festgehalten (Ansicht *FX-Trades*). Währungspositionen mit
Gewinn/Verlust aus Kursbewegungen gibt es nicht.
*Details:* [Architektur und Import-Pipeline](10-architektur-und-pipeline.md), § 5.3.

#### Cash im Kontostand nur in EUR und USD

Die Kontostände aus dem Kontoauszug kennen genau zwei Währungen; Cash in einer dritten Währung
wird stillschweigend nicht erfasst.
*Details:* [Architektur und Import-Pipeline](10-architektur-und-pipeline.md), § 8.2
„`account_snapshots`“.

### 1.2 Optionen: Verfall, Ausübung, Zuteilung

#### Ausübung eigener Optionen ohne Verknüpfung zur Aktie

Bei einer *Zuteilung* werden Option und gelieferte Aktien über eine gemeinsame Kennung
verknüpft (für die Spreads-Auswertung und die Detailseiten). Bei einer *Ausübung* eigener Long-
Optionen fehlt diese Verknüpfung.
*Details:* [Architektur und Import-Pipeline](10-architektur-und-pipeline.md), § 5.5.

### 1.3 Splits

#### Optionen auf eine gesplittete Aktie werden nicht umgestellt

Der Split wird erkannt, offene Options-Positionen bleiben aber unter dem alten Kontrakt stehen.
Ein späterer Verfall oder Rückkauf unter dem neuen Kontrakt eröffnet dann eine falsche
Gegenposition. Kapitalmaßnahmen mit mehr als zwei Zeilen (mehrere Strikes) passen außerdem nicht
ins Paar-Schema der Split-Verarbeitung.
*Schon vorgekommen:* einmal, bei einem Forward Split mit offenem Spread; zu Reverse Splits mit
offener Option fehlen noch Daten. *Details:* [Architektur und
Import-Pipeline](10-architektur-und-pipeline.md), § 6.2 „Fall SPLIT“.

### 1.4 Spread-Erkennung

#### Rolls werden als Spread erkannt

Ein Roll als Combo-Order (alte Option zurückkaufen, neue verkaufen) sieht aus wie ein Calendar-
oder Diagonal-Spread. Die neu verkaufte Option erscheint dann in der Spreads-Ansicht als
„Spread“ mit nur einem Leg.
*Schon vorgekommen:* ja. *Details:* [Architektur und Import-Pipeline](10-architektur-und-pipeline.md),
§ 5.4.

#### Schließende Combo-Orders heißen „umgekehrt“

Wer einen Bull Put Spread per Combo-Order zurückkauft, sieht die Schließung in *Raw Data* als
„Bear Put Spread“. Die Spreads-Auswertung ist davon nicht betroffen, sie verwendet die Strategie
der Eröffnung.
*Schon vorgekommen:* ja, regelmäßig. *Details:* wie oben.

#### Nicht erkannte Strategien lassen sich nicht von Hand zusammenfassen

Erkannt wird nur, was als Combo-Order oder innerhalb derselben 3 Sekunden ausgeführt wurde.
Einzeln mit Abstand eingegebene Legs, Legs an verschiedenen Tagen und Ratio Spreads bleiben
Einzeloptionen — auch wenn man selbst weiß, dass sie zusammengehören. Eine manuelle Zuordnung ist
geplant; schwierig sind dabei vor allem Calendar-Spreads, deren Legs zu verschiedenen Terminen
enden. Ein Iron Butterfly heißt außerdem „Iron Condor“.
*Details:* [Architektur und Import-Pipeline](10-architektur-und-pipeline.md), § 5.4.

### 1.5 Vorgaben von IBKR

Keine Grenzen des Journals, aber wichtig zu wissen:

- Eine Flex Query lässt sich je Abruf für höchstens **365 Tage** starten.
- **Paper-Konten** liefern nur die letzten rund **180 Tage** — Trades wie Kontoauszüge.
- **Kontostände** gibt es nur aus dem täglichen Kontoauszug; rückwirkend nur Tag für Tag von Hand.
- Die **Web-API** verträgt keine häufigen Abrufe; zu viele (fehlgeschlagene) Anfragen führen zu
  einer vorübergehenden Sperre.

*Details:* Benutzerhandbuch [TradingJournal-Weaver installieren](../benutzer/40-weaver-installieren.md),
Abschnitt 8, und [Alltag mit dem TradingJournal](../benutzer/70-alltag.md), Abschnitt 1.

---

## 2. Ungetestet — Beispiele gesucht

Für einige Fälle gibt es im Code eine Behandlung oder eine naheliegende Erwartung, aber keine
echten Daten, an denen sie geprüft wurde — etwa ein Aktiensplit während einer offenen Option,
Forward Splits, Teil- und vorzeitige Zuteilungen, die Ausübung eigener Optionen, Fusionen und
Spin-offs, Futures oder ein Konto mit anderer Basiswährung als EUR.

Die vollständige Liste mit dem, was jeweils schon bekannt ist, konkreten Fragen und den
hilfreichen Daten steht in einem eigenen Dokument im Repository:
[Beispiele gesucht](https://github.com/mike-1140/TradingJournal/blob/master/BEISPIELE-GESUCHT.md).
Was davon als Nächstes umgesetzt wird, zeigt die
[Roadmap](https://github.com/mike-1140/TradingJournal/blob/master/ROADMAP.md).

---

## 3. Mithelfen

Wer einen der Fälle aus [Beispiele gesucht](https://github.com/mike-1140/TradingJournal/blob/master/BEISPIELE-GESUCHT.md)
im eigenen Konto hat, kann sehr helfen — mit der **Flex-Query-XML** des betreffenden Tages:

1. Im Kundenportal die Flex Query für den Tag des Ereignisses starten (siehe Benutzerhandbuch
   [TradingJournal-Weaver installieren](../benutzer/40-weaver-installieren.md), Abschnitt 8) oder
   die Datei aus `C:\Trade_XML\<environment>\<benutzer>\processed` nehmen.
2. **Anonymisieren:** In einem Text-Editor die **Kontonummer** überall ersetzen (z. B. durch
   `U1234567` bzw. bei Paper `DU1234567`) — sie steht im Kopf jedes Tagesberichts und an jedem
   Trade. Steht ein Konto-Pseudonym oder Name in der Datei, auch diesen ersetzen. Trade-IDs,
   Kurse und Mengen bitte lassen, sonst ist der Fall nicht nachvollziehbar.
3. Den Fall melden: kurz beschreiben, was passiert ist (z. B. „Reverse Split 1:10 auf XYZ
   während offener Short-Put-Position“), was das Journal anzeigt und was richtig wäre — die
   anonymisierte Datei anhängen. Am besten im **Forum**, in dem das TradingJournal vorgestellt
   wurde; wiederkehrende Fragen fließen dort in eine FAQ ein. Wer ein GitHub-Konto hat, kann
   stattdessen im Repository `TradingJournal-Weaver` ein Issue mit der Vorlage
   [„Beispiel für ungetesteten Fall“](https://github.com/mike-1140/TradingJournal-Weaver/issues/new?template=beispiel.yml)
   anlegen — sie fragt Fall-Nummer, Ablauf und die Anonymisierung ab.

> [!CAUTION]
> Die Flex-Query-XML enthält vollständige Handelsdaten. Vor dem Hochladen prüfen, dass die
> Kontonummer wirklich überall ersetzt ist (Suchen nach den letzten vier Ziffern). Prüfcodes
> (Tokens) stehen in der XML nicht, gehören aber auch sonst nie in einen Forenbeitrag oder ein
> Issue.
