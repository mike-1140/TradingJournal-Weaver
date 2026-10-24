# Roadmap

Was als Nächstes an **TradingJournal** und **TradingJournal-Weaver** geplant ist. Das Projekt ist
ein Hobbyprojekt — es gibt deshalb **keine Termine**, und die Reihenfolge kann sich ändern. Fehler,
die zu falschen Zahlen führen, haben immer Vorrang vor neuen Funktionen.

Vorschläge und Wünsche gerne im Forum, in dem das TradingJournal vorgestellt wurde (später auch
als GitHub-Issue). Für einige Punkte fehlen echte Beispieldaten — welche, steht in
[Beispiele gesucht](BEISPIELE-GESUCHT.md).

Die bekannten Grenzen des heutigen Stands beschreibt das technische Handbuch:
[Bekannte Grenzen und offene Fragen](docs/handbuch/technik/90-bekannte-grenzen.md).

---

## Als Nächstes — Korrektheit

Fehler oder Lücken, die Positionen, Kampagnen oder Ergebnisse verfälschen können.

- **Splits bei offenen Optionen und Spreads** — Bei einem Aktiensplit werden offene
  Options-Positionen heute nicht auf den neuen Kontrakt umgestellt; ein späterer Verfall oder
  Rückkauf eröffnet dann eine falsche Gegenposition. *Braucht Beispieldaten* (siehe
  [Beispiele gesucht](BEISPIELE-GESUCHT.md), Fall 1).
- **Status bei Teilschließung** — Wird nur ein Teil einer Option zugeteilt oder verfällt eine in
  mehreren Tranchen eröffnete Option, steht *Closed* statt *Assigned*/*Expired*. Ergebnis und
  Abschlussart stimmen bereits.
- **Ausübung eigener Optionen** — Bei einer Zuteilung werden Option und gelieferte Aktien
  verknüpft, bei der Ausübung eigener Long-Optionen noch nicht.
- **Warnung bei Trades in falscher Reihenfolge** — Kommen ältere Trades nach jüngeren an (etwa
  beim Nachholen alter Berichte), soll der Import deutlich warnen statt still falsch zu buchen.
- **Andere Kapitalmaßnahmen erkennen** — Fusionen, Spin-offs oder Symbolwechsel werden heute wie
  normale Trades zum Preis 0 verarbeitet. Erster Schritt: erkennen und warnen. *Braucht
  Beispieldaten* (Fall 6).
- **Rolls nicht als Spread erkennen** — Ein Roll per Combo-Order erscheint heute als Calendar-
  bzw. Diagonal-Spread mit nur einem Bein. Schließende Combo-Orders sollen vor der
  Strategie-Erkennung herausgefiltert werden. *Braucht Beispieldaten* (Fall 7).
- **Iron-Condor-Grafik** — Die Strukturgrafik auf der Detailseite eines Iron Condors bleibt leer.

## Später — Komfort und Auswertung

- **USD/EUR-Umschalter** — Alle Beträge liegen bereits in beiden Währungen vor, angezeigt werden
  beide aber nur auf den Detailseiten geschlossener Trades. Ziel: Umschalten per Klick oder
  EUR-Werte überall.
- **Strategien von Hand zusammenfassen** — Nicht erkannte Spreads (Legs einzeln oder an
  verschiedenen Tagen eingegeben, Ratio Spreads) in der Oberfläche zu einer Strategie
  zusammenfassen; falsche Zuordnungen auflösen.
- **Zeitraumfilter auf allen Seiten** — Der globale Zeitraumfilter gilt noch nicht überall.
- **Python 3.15** — Heute ist Python 3.14 vorgeschrieben, weil nicht alle benötigten Pakete für
  3.15 bereitstehen.
- **Linux und macOS** — Heute läuft alles nur unter Windows. Erster Schritt: die fest
  eingetragenen Ablageordner (`C:\Trade_XML`, `C:\Trade_CSV`) einstellbar machen. Hilfsskripte,
  Handbuch und Tests für andere Systeme folgen nur, wenn genug Nachfrage besteht.

## Ideen — noch nicht entschieden

- **Disziplin in Euro** — Regelbrüche aus dem Psychologie-Modul in Geld beziffern (geplanter
  gegenüber tatsächlichem Trade).
- **Kalender-Heatmap** — Gewinn/Verlust je Tag als Kalender, auch als Dashboard-Kachel.
- **Dashboard per Drag & Drop** — Kacheln nicht nur ein- und ausblenden, sondern frei anordnen.
- **GitHub Discussions** — Fragen und Austausch direkt auf GitHub, sobald das Forum dafür nicht
  mehr reicht.

---

## Erledigt (Auswahl)

- **v1.1.0 — öffentliche Freigabe:** Quellcode öffentlich (PolyForm Noncommercial), Handbücher
  als PDF, öffentliche Demo mit echten, anonymisierten Trades bis September 2026.
- `db-backup.ps1`: alle Datenbanken sichern und wiederherstellen, mit automatischer Sicherung vor
  jedem Einspielen.
- Kampagnen-Frist (`MAX_GAP_DAYS`) per `.env` einstellbar.
- Ansicht *FX-Trades* für Währungstausch, Teilausführungen zusammengefasst.
- Eingebautes Handbuch in der App (Menüpunkt *Hilfe*).
