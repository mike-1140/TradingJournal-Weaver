# Alltag mit dem TradingJournal

Beschreibt den betrieblichen Ablauf aus Nutzersicht: was täglich automatisch passiert, wie
Kampagnen im UI "leben", und welche manuellen Workflows (Trade Log, Psychology) es
zusätzlich zur reinen Datenanzeige gibt. Für die technische Pipeline-Architektur siehe
[`docs/handbuch/technik/10-architektur-und-pipeline.md`](../technik/10-architektur-und-pipeline.md).

---

## 1. Datenimport

Läuft über einen einzigen Einstiegspunkt in `TradingJournal-Weaver`:

```bash
python run_pipeline.py
```

Gesteuert durch `TradingJournal-Weaver/pipeline.toml` — Standard-Schrittfolge:

```
fetch_emails → fetch_api → snapshot_csv → import → process → summary
```

| Schritt        | Was passiert                                                                                                                                                                   |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `fetch_emails` | IBKR FlexQuery-XML + Activity-CSV per IMAP abrufen → `C:\Trade_XML\incoming_mail\` / `C:\Trade_CSV\incoming\`                                                                  |
| `fetch_api`    | Zweiter, gleichwertiger Kanal: FlexQuery direkt per Web-API → `C:\Trade_XML\incoming_api\` (No-Op ohne konfiguriertes `IBKR_FLEX_QUERIES`)                                     |
| `snapshot_csv` | NAV-Tagesschnappschüsse (`account_snapshots`) aus den Activity-CSVs — einziger aktiver Weg, TWRR exakt zu bestimmen                                                            |
| `import`       | Beide XML-Quellordner → `trades_raw`, Routing per `accountId` → User/Environment (`accounts.toml`), Checksum-Dedup verhindert Doppel-Import über beide Kanäle                 |
| `process`      | FIFO-Matching: `trades_raw` → `trades_open`/`trades_close`/`trading_campaigns`/`campaign_ledger`                                                                               |
| `summary`      | Verarbeitete XML-Berichte (Mail und API) in `summary_<prefix><env>.xml` zusammenfassen (Basis für spätere `--from-summary`-Rebuilds)                                           |

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
> Import aus der Sammeldatei, siehe Abschnitt 6). Die Sammeldatei ist nach Datum sortiert und
> enthält auch die nachgeholten Tage, beim Neuaufbau stimmt die Reihenfolge also wieder. Der
> Neuaufbau legt die Tabellen dieses Environments neu an — neben Trades und Kampagnen gehen
> dabei auch die Einträge im **Trade Log** und die **Kontostände** verloren. Die Kontostände lassen sich wiederherstellen, indem die
> verarbeiteten CSV-Dateien aus `C:\Trade_CSV\incoming\<benutzer>\processed` zurück nach
> `C:\Trade_CSV\incoming` kopiert werden; Trade-Log-Einträge vorher sichern (Datenbank-Backup).

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
> vorübergehenden Sperre (Fehler 1025, siehe [Fehlerbehebung](90-fehlerbehebung.md)).
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

`pipeline.toml` definiert, **welche** User × Environments verarbeitet werden — die Datei
ist maschinenspezifisch (wie `.env`, nicht versioniert, siehe `pipeline.toml.example`):
jede Maschine trägt nur die User/Environments ein, die dort tatsächlich per
`reset_IBKR_DB.py` initialisiert wurden. Beispiel mit zwei Nutzern:

| User | Environments                           |
| ---- | --------------------------------------- |
| anna | money, paper, autom_money, autom_paper  |
| tom  | money                                   |

Für den automatisierten Lauf (z. B. täglich per Windows-Aufgabenplanung) siehe
[Technisches Handbuch: Server-Betrieb — TradingJournal auf einem eigenen Server](../technik/70-server-betrieb.md).

## 2. Kampagnen-Lebenszyklus aus Nutzersicht

Jede Position (Aktie oder Options-Strategie) je Symbol bildet eine **Kampagne**:

```
Erster Trade im Symbol           → Kampagne ACTIVE
Position komplett glattgestellt  → Kampagne PENDING
10 Tage ohne neue Aktivität      → Kampagne CLOSED
Neue Aktivität innerhalb 10 Tage → zurück auf ACTIVE (z. B. Roll, Wheel-Fortsetzung)
```

Das ermöglicht z. B. Wheel-Strategien (Put verkauft → Assignment → Covered Call → Call
läuft aus → neuer Put) als **eine zusammenhängende Kampagne** statt vieler Einzeltrades.
In der UI: `Campaigns`-Liste (offen/geschlossen), `CampaignDetail` zeigt den vollständigen
Ledger-Verlauf inkl. P&L-Verlaufsdiagramm (kumulierter `cum_pnl` aus `campaign_ledger`).

## 3. Tägliche Nutzung der UI

Nach dem Import (typischerweise Vortagesdaten) ein üblicher Rundgang:

1. **Dashboard** — KPIs für das gewählte Environment (Profit Factor, Max Drawdown,
   NAV/TWRR aus `account_snapshots`, konfigurierbare Kacheln)
2. **Aktivität** (`/stats/activity`) — Ledger-Detailansicht über alle Ticker der letzten
   Tage (Load-more), schneller Überblick "was ist zuletzt passiert" ohne pro Symbol in die
   Kampagne zu wechseln
3. **Campaigns / Spreads / Symbols** — bei Bedarf Detailanalyse einzelner Positionen

## 4. Trade Log — Entscheidungsjournal

Route `/log`, ergänzt die reine Datenanzeige um geplante/reflektierte Entscheidungen
(Tabelle `trade_planner`, optional per `campaign_id` mit der echten Kampagne verknüpft):

- **Vor dem Trade** (`/log/neu` oder Quick-Entry `/log/schnell?env=MONEY&prefix=dein_user_`):
  Entry-Plan erfassen — IV Percentile/Rank, Strategie, Legs (`trade_planner_legs`),
  Mindset, Confidence, Pre-Mortem ("was könnte schiefgehen")
- **Nach dem Trade:** Ist-Werte nachtragen — Exit-Preis, realisiertes P&L, tatsächliche
  DTE, Plan-Einhaltung (`plan_adherence`), Lessons Learned
- Zweck: Soll/Ist-Abgleich der eigenen Entscheidungsqualität, nicht nur der reinen Zahlen

## 5. Psychology-Modul

Ergänzendes Journal-System (`psychology_rulesets`/`psychology_rules`,
`psychology_entries`, `psychology_compliance_results`):

1. Eigene Handelsregeln als Regelwerk (Ruleset) hinterlegen — z. B. "keine Trades bei
   IV Rank < 20", "max. 3 offene Positionen gleichzeitig"
2. Zu einem Trade ein Journal-Entry anlegen
3. System prüft den Entry automatisch gegen das aktive Regelwerk und speichert das
   Ergebnis in `psychology_compliance_results` — sichtbar in `PsychologyAnalytics`

Bewusst getrennt vom Trade Log: Trade Log ist Plan/Reflexion je Trade, Psychology-Modul
ist die systematische Regel-Compliance über die Zeit.

## 6. Manuelle Eingriffe / Wartung

| Situation                                                                               | Vorgehen                                                                                                                                               |
| ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Neue/geänderte Import-Logik an einer echten XML testen, ohne Produktivdaten zu berühren | XML nach `C:\Trade_XML\test\<user>\incoming\` legen, `python run_pipeline.py` — landet automatisch in der TEST-DB (siehe `docs/handbuch/technik/30-befehlsreferenz.md` § TEST-Environment) |
| Offene Position liegengeblieben (Open importiert, Close nie gekommen — z. B. Datenlücke) | `TradingJournal-Weaver/tools/maintenance/cleanup_stale_positions.py` (Dry-Run ist Standard, erst mit `--execute` löschen)                                            |
| Kompletter Neuaufbau eines Environment/Prefix (z. B. nach Trades in falscher Reihenfolge, siehe Abschnitt 1) | `reset_IBKR_DB.py` (⚠️ destruktiv — löscht auch Trade Log und Kontostände) + Re-Import über `--from-summary`                                                                                   |

## 7. Multi-User-Betrieb

Jeder Nutzer hat einen eigenen Tabellen-Prefix und eigene IBKR-Konten (Zuordnung per
`accountId` in `accounts.toml`). In der UI loggt sich jeder mit eigenem Account ein; ein
Admin-Account kann zusätzlich über "Nutzer wechseln" in die Sicht eines anderen Users
springen (siehe [Erster Start — UI-Erstkonfiguration](60-erster-start.md) Abschnitt 3).

---

## Weiterführende Dokumentation

| Datei                                | Inhalt                                           |
| ------------------------------------- | ------------------------------------------------- |
| `docs/handbuch/technik/10-architektur-und-pipeline.md` | Technischer Datenfluss, FIFO-Logik, DB-Schema, Config-Zusammenspiel |
| `docs/handbuch/technik/30-befehlsreferenz.md`              | Befehlsreferenz aller Scripts                    |
| `docs/handbuch/benutzer/60-erster-start.md`         | Erstkonfiguration der UI                         |
| `docs/handbuch/technik/70-server-betrieb.md`    | Alternative Installation: eigener Server statt lokaler PC |
