# Architektur und Import-Pipeline

**Projekt:** TradingJournal-Weaver — Trading-Journal Import-System  
**Ziel:** Vollständige Dokumentation des Datenflusses von IBKR-Rohdaten (XML/CSV) bis zur befüllten MySQL-Datenbank

---

## Inhaltsverzeichnis

1. [Überblick & Ziele](#1-überblick--ziele)
2. [Datenquellen](#2-datenquellen)
3. [Pipeline-Architektur](#3-pipeline-architektur)
4. [Phase 0 — E-Mail-Abruf](#4-phase-0--e-mail-abruf-get_flexquery_emailspy)
5. [Phase 1 — Import (XML/CSV → trades_raw)](#5-phase-1--import-xmlcsv--trades_raw)
6. [Phase 2 — Processing (trades_raw → Endtabellen)](#6-phase-2--processing-trades_raw--endtabellen)
7. [Kernkonzepte](#7-kernkonzepte)
8. [Datenbankstruktur](#8-datenbankstruktur)
9. [Konfiguration & Multi-User](#9-konfiguration--multi-user)
10. [Fehlerbehandlung & Robustheit](#10-fehlerbehandlung--robustheit)
11. [Ausblick — Erweiterungen & Verbesserungen](#11-ausblick--erweiterungen--verbesserungen)

---

## 1. Überblick & Ziele

### Was ist das System?

Das TradingJournal ist eine **Webanwendung, die auf dem eigenen Rechner (oder einem eigenen
Server) läuft** und im Browser bedient wird — weder eine App aus einem App-Store noch eine
Online-Plattform. Es besteht aus zwei Programmen, die sich eine MySQL-Datenbank teilen:
**TradingJournal-Weaver** (Python, ohne eigene Oberfläche) holt und verarbeitet die Daten,
**TradingJournal** (Laravel) zeigt sie im Browser an. Dieses Kapitel beschreibt vor allem den
Weaver-Teil.

Das System liest automatisch **IBKR FlexQuery-Reports** (XML) und **Activity Statements** (CSV) ein und überführt die Rohdaten in ein strukturiertes Trading-Journal mit:

- **FIFO-Lot-Matching** für Aktien und Optionen (Devisentausch wird separat erfasst, ohne FIFO)
- **Kampagnen-Tracking** (gebündelte Trades je Symbol/Zeitraum)
- **Options-Strategie-Erkennung** (Spreads, Iron Condors, Straddles, …)
- **Vollständigem Audit-Trail** (jede Aktion im `campaign_ledger`)
- **Multi-User/Multi-Environment-Support** (Echtgeld, Paper, Test, Automatisiert)

### Warum zwei Phasen?

Die Trennung in **Import** (XML → `trades_raw`) und **Processing** (Matching + Kampagnen) ist bewusst gewählt:

| Vorteil | Erklärung |
|---|---|
| **Wiederholbarkeit** | Import kann mehrfach ausgeführt werden (Checksums verhindern Doppelimport) |
| **Debugging** | `trades_raw` zeigt exakt was IBKR geliefert hat, unverändert |
| **Trennung von Verantwortlichkeiten** | Parser-Logik vs. Business-Logik klar getrennt |
| **Datenbank-Reset** | `reset_IBKR_DB.py` setzt **alle** Tabellen zurück (inkl. `trades_raw`) — Summary-Files ermöglichen den vollständigen Neuaufbau der Trades ohne Originaldateien (Kontoauszüge/`account_snapshots` sind nicht enthalten) |

---

## 2. Datenquellen

### 2.1 FlexQuery XML

IBKR generiert **täglich** einen FlexQuery-Report als XML. Die Datei enthält alle Aktivitäten des Kontos für den gewählten Zeitraum.

**Struktur:**
```xml
<FlexQueryResponse>
  <FlexStatements>
    <FlexStatement accountId="U1234567" fromDate="..." toDate="...">
      <Trades>
        <Trade tradeID="..." symbol="AAPL" buySell="BUY" quantity="100" ... />
        <Trade tradeID="..." assetCategory="CASH" symbol="EUR.USD" ... />
      </Trades>
      <OptionEAE>
        <OptionEAE tradeID="..." transactionType="Expiration" ... />
      </OptionEAE>
      <CorporateActions>
        <CorporateAction type="RS" symbol="APDN.OLD" quantity="-1500" ... />  <!-- Reverse Split 1:50, alter Teil -->
        <CorporateAction type="RS" symbol="APDN" quantity="30" ... />        <!-- neuer Teil, gleiche actionID -->
      </CorporateActions>
    </FlexStatement>
  </FlexStatements>
</FlexQueryResponse>
```

**Asset-Kategorien:**
| Code | Bedeutung | Beispiel |
|---|---|---|
| `STK` | Aktien | AAPL, TSLA |
| `OPT` | Optionen | AAPL 250117C00150000 |
| `CASH` | FX-Trades | EUR.USD, GBP.USD |

### 2.2 Activity Statement CSV

IBKR liefert täglich auch ein **Activity Statement CSV** — ein mehrteiliges Dokument mit Kontosnapshots (Cash, Net Liquidation, Margin, etc.). Es enthält **keine Einzeltrades**, sondern Kontostands-Daten.

Die CSV landet in einem **separaten Verzeichnis**: `C:\Trade_CSV\incoming\`
(nur per Mail — kein API-Äquivalent für Activity Statements, siehe Phase 0).
XML-Files kommen nach `C:\Trade_XML\incoming_mail\` (Mail) bzw. `C:\Trade_XML\incoming_api\`
(FlexQuery Web-API, zweiter gleichwertiger Kanal für Trades).

`C:\Trade_XML\incoming_mail\` und `C:\Trade_CSV\incoming\` werden über
`get_flexquery_emails.py` befüllt, `C:\Trade_XML\incoming_api\` über `get_flexquery_api.py`
(siehe Phase 0).

### 2.3 OptionEAE und BookTrades

IBKR erzeugt bei **automatischen Schließungsereignissen** (Verfall, Ausübung, Assignment) zwei Arten von Einträgen im XML:

- **OptionEAE** (im `<OptionEAE>`-Block): Enthält das *Ereignis* mit Typ und Details (`Expiration`, `Exercise`, `Assignment`, `Cash Settlement`). Aus diesem Block werden die Informationen gewonnen, um BookTrades korrekt zu klassifizieren.
- **BookTrade** (im `<Trades>`-Block, `transactionType="BookTrade"`): Der dazugehörige automatische *Trade-Eintrag*, den IBKR für die Buchung erzeugt. Allein stehend hat er noch keinen Status.

`book_trades.py` liest die OptionEAE-Daten und überträgt den jeweiligen Ereignistyp auf den passenden BookTrade — verbunden via `tradeID` oder `conid+date` — und verknüpft bei einer Zuteilung die Option per `linkID` mit dem Aktien-Trade (Details § 5.5).

---

## 3. Pipeline-Architektur

### 3.1 Gesamtübersicht

```
┌──────────────────────────────────────────────────────────┐
│  PHASE 0: E-MAIL-ABRUF + FLEXQUERY-API (zwei Kanäle)     │
│  get_flexquery_emails.py               get_flexquery_api.py│
│  ├── IMAP-Postfach (IBKR-Mails)        ├── FlexQuery Web-API│
│  ├── FlexQuery-XML → incoming_mail\    └── FlexQuery-XML → │
│  └── Activity-CSV  → C:\Trade_CSV\         incoming_api\   │
│        incoming\                                          │
└──────────────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────┐
│                    DATENQUELLEN                          │
│   C:\Trade_XML\incoming_mail\  + incoming_api\           │
│   └── *.xml  ← FlexQuery: Trades, OptionEAE,             │
│                 CorporateActions (in beiden Ordnern,     │
│                 sofern die API-Query gleich konfiguriert)│
│   C:\Trade_CSV\incoming\                                 │
│   └── U1234567_20250117.csv  ← Activity Statement        │
│                                 (Kontostands-Snapshots)  │
└──────────────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────┐
│  PHASE 1: IMPORT                                         │
│  import_ibkr_trades.py                                   │
│                                                          │
│  flex_parser.py (Orchestrator)                           │
│  ├── day_trade_processor.py   → Trades, OptionEAE,       │
│  │                               CorporateActions        │
│  ├── option_strategies.py     → Spread-Erkennung         │
│  ├── book_trades.py           → BookTrade-Matching       │
│  └── Checksum-Prüfung         → Duplikat-Schutz          │
│                                                          │
│  INSERT → trades_raw (processed=0)                       │
│  INSERT → trades_fx (FX-Trades separat)                  │
└──────────────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────┐
│  PHASE 2: PROCESSING                                     │
│  process_ibkr_trades.py                                  │
│                                                          │
│  inventory_tracker.py    → Kampagnen-Lebenszyklus        │
│  open_trade.py           → FIFO-Lot-Schema               │
│  closed_trade.py         → Closed-Trade-Schema           │
│                                                          │
│  Ergebnis:                                               │
│  ├── trades_open          ← Aktive FIFO-Tranchen         │
│  ├── trades_close         ← Abgeschlossene Trades        │
│  ├── trading_campaigns    ← Kampagnen je Symbol          │
│  └── campaign_ledger      ← Vollständiges Audit-Log      │
└──────────────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────┐
│  PHASE 3: (OPTIONAL) SUMMARY                             │
│  xml_append_summary.py                                   │
│  └── Erstellt Zusammenfassungs-XML für nächsten Import   │
└──────────────────────────────────────────────────────────┘
```

### 3.2 Pipeline-Runner

Alle Schritte werden über `run_pipeline.py` gesteuert:

```bash
python run_pipeline.py                     # alle Schritte
python run_pipeline.py --steps import      # nur Import
python run_pipeline.py --steps process     # nur Processing
python run_pipeline.py --envs money        # nur Echtgeld
python run_pipeline.py --users dein_user   # nur User dein_user
```

**`pipeline.toml` — Konfiguration:**
```toml
[settings]
steps = ["fetch_emails", "fetch_api", "snapshot_csv", "import", "process", "summary"]
#        ↑ Phase 0 Mail  ↑ Phase 0 API ↑ Snapshots    ↑ Phase 1  ↑ Phase 2  ↑ Phase 3

[users.dein_user]
environments = ["money", "paper", "autom_money", "autom_paper"]

[users.zweiter_user]
environments = ["money"]
```
Tabellen-Prefix kommt aus `users.toml` (zentrale, lokale Registry, siehe § 9.1) — in
`pipeline.toml` nur bei Bedarf per `prefix = "..."` explizit überschreibbar.

`account_snapshots` kommt ausschließlich aus dem Kontoauszug (CSV per Mail) über
`snapshot_csv`, siehe § 8.2 — die Flex Queries enthalten keine Kontostands-Daten.

Der `import`-Step läuft ohne `--users`/`--envs`-Filter **einmal global** (accountId-Routing
deckt intern alle User/Envs ab); mit gesetztem Filter erzeugt `run_pipeline.py` einen
Task pro passendem User × Environment und nutzt dafür das CLI-Override
`import_ibkr_trades.py <env> <prefix>` (§ 5.1).

---

## 4. Phase 0 — E-Mail-Abruf (`get_flexquery_emails.py`)

IBKR stellt FlexQuery-Reports und Activity Statements **automatisiert per E-Mail** zu. `get_flexquery_emails.py` übernimmt den Abruf und die Verteilung in die richtigen Eingangsverzeichnisse.

```
get_flexquery_emails.py
│
├── Verbindet sich per IMAP mit dem konfigurierten Postfach (.env)
├── Durchsucht Inbox nach IBKR-Report-Mails (Betreff-Filter)
│
├── Für XML-Anhänge (FlexQuery-Report):
│   └── Speichert in C:\Trade_XML\incoming_mail\
│       (enthält Trades, OptionEAE, CorporateActions)
│
├── Für CSV-Anhänge (Activity Statement):
│   └── Speichert in C:\Trade_CSV\incoming\
│       (enthält Kontostands-Snapshots, keine Einzeltrades)
│
└── Löscht verarbeitete IBKR-Mails aus dem Postfach
```

**Konfiguration in `.env`:**
```ini
IMAP_USERNAME=trading@example.com
IMAP_PASSWORD=...
IMAP_SERVER=imap.gmx.com
IBKR_ACTIVITY_SUBJECT=Activity Statement
IBKR_ACTIVITY_SUBJECT_DE=Kontoauszug
```

**Wichtig:** Phase 0 ist optional — XML/CSV-Dateien können auch manuell in die Eingangsverzeichnisse kopiert werden. Die nachfolgenden Phasen 1 und 2 sind davon unabhängig. Ein Namensmuster ist im Normalbetrieb **nicht** erforderlich (siehe Phase 1) — nur der dedizierte TEST-Modus verlangt `flex.*.xml`.

**Zweiter Kanal `fetch_api` (`get_flexquery_api.py`):** Abruf der FlexQuery-XMLs direkt über die IBKR-Web-API (`.env`: `IBKR_FLEX_QUERIES=token:query_id,...`), läuft in `pipeline.toml` gleichwertig neben `fetch_emails` als zweite produktive Quelle für `trades_raw`. Schreibt nach `C:\Trade_XML\incoming_api\` (getrennt von `incoming_mail\`, damit beide Quellen unabhängig nachvollziehbar bleiben); der `import`-Step scannt **beide** Ordner. Checksum-Dedup verhindert doppelte Trades, falls dieselben Daten über beide Kanäle ankommen. Ist die API-Query mit denselben Sektionen eingerichtet wie die Mail-Query (Trades, Option Exercises/Assignments/Expirations, Corporate Actions), liefert sie auch `OptionEAE`/BookTrades und CorporateActions. Timing: Der Report wird bei Anfrage on-demand generiert, es gibt kein festes Tages-Zeitfenster — die Daten des Vortags stehen in der Regel schon am frühen Morgen bereit. Retry-Logik fängt die kurze "noch in Verarbeitung"-Phase ab (typisch wenige Sekunden, bis ~30s bei Accounts mit geringerer IBKR-Priorität, z.B. Paper-Konten). Damit auch ein unabhängiger zweiter Kanal für Ausfallsicherheit, falls die Mail an einem Tag ausbleibt.

---

## 5. Phase 1 — Import (XML/CSV → trades_raw)

### 5.1 Einstiegspunkt: `import_ibkr_trades.py`

```
import_ibkr_trades.py
│
├── Für jede *.xml-Datei (aus C:\Trade_XML\incoming_mail\ UND incoming_api\,
│   incoming_mail zuerst — Quelle ist fuer den Import irrelevant):
│   ├── Lese <FlexStatement> (kann mehrere je Datei enthalten)
│   ├── Extrahiere accountId → route zu Environment/User (via config.py)
│   ├── Rufe flex_parser.process_flex_file() auf
│   └── Verschiebe Datei in <env>/<user>/processed/ oder deleted/
└── Scanne C:\Trade_CSV\incoming\ nach CSV-Dateien:
    └── activity_csv_parser → account_snapshots
```

**Kein Dateinamen-Filter (Normalbetrieb):** Verarbeitet werden alle `*.xml`-Dateien
in beiden Ordnern, unabhängig vom Namen — Mail- und API-Dateien haben verschiedene
Namensschemata. Einzige Ausnahme: der TEST-Modus (`test\<user>\incoming\`)
verlangt weiterhin `flex.*.xml`.

**CLI-Override — gezielt ein Environment importieren:**
```bash
python -m src.import_ibkr_trades money dein_user_
```
Analog zu `process_ibkr_trades.py`: nur Dateien, deren accountId auf dieses
Environment/Prefix routet, werden importiert und verschoben — alle anderen bleiben
in `incoming_mail\`/`incoming_api\` liegen. `run_pipeline.py` nutzt diesen Modus
automatisch, sobald `--users`/`--envs` gesetzt sind (§ 3.2).

**Routing via `accounts.toml` (`src/config.py` → `get_account_config()`):**

Das Mapping steht — wie `pipeline.toml` — in einer maschinen-/personenspezifischen,
nicht versionierten Datei (`accounts.toml`, Vorlage `accounts.toml.example`), nicht
im Code:
```toml
# Key = letzte 4 Ziffern der IBKR accountId
# "U***1234" und "U12341234" ergeben denselben Key "1234"
[1234]
user = "dein_user"
environment = "money"
```
Tabellen-Prefix steht bewusst nicht hier, sondern wird zur Laufzeit aus `users.toml`
aufgelöst (`get_account_config()`) — einzige Quelle für `user → prefix` im Projekt.

Neue IBKR-Konten müssen in `accounts.toml` ergänzt werden — XMLs mit unbekannter accountId werden beim Import übersprungen (Warnung im Log). Neue User zusätzlich in `users.toml` eintragen.

Jede XML-Datei enthält immer nur Daten eines einzigen Kontos. Die `accountId` im `<FlexStatement>` bestimmt, welchem User und Environment die Trades zugeordnet werden.

### 5.2 Kern-Parser: `flex_parser.py`

Der Flex-Parser ist der **Orchestrator** der Import-Phase. Er koordiniert alle Sub-Parser.

```
process_flex_file(xml_path, db, repo, logger, environment)
│
├── 1. Extrahiere Rohdaten (parallel als DataFrames):
│   ├── extract_trades_for_db()          → df_trades
│   ├── extract_optioneae_for_db()       → df_eae
│   └── extract_corporateaction_for_db() → df_corp
│
├── 2. Aggregiere gleichartige Trades:
│   └── Gruppenbildung: (conid, symbol, buySell, ibOrderID)
│       Hintergrund: Exchange-Fills können in mehreren Teil-Trades kommen
│
├── 3. Options-Strategie-Erkennung:
│   └── option_strategies.detect_strategies(df_trades)
│
├── 4. BookTrade-Matching:
│   └── book_trades.handle_booktrades(df_trades, df_eae)
│
├── 5. CorporateActions sortieren:
│   └── sort_corporate_actions(df_corp)
│
├── 6. Checksum-Berechnung & Duplikat-Check:
│   ├── MD5(tradeID + datetime + symbol + qty + price)
│   └── SELECT checksums FROM trades_raw WHERE checksum IN (...)
│
├── 7. Symbol-Lookup/-Anlage:
│   └── get_symbols_bulk() → INSERT neue Instrumente
│
└── 8. INSERT in Datenbank:
    ├── INSERT INTO trades_raw (processed=0)
    └── INSERT INTO trades_fx
```

### 5.3 Element-Extraktion: `day_trade_processor.py`

**Normale Trades (`extract_trades_for_db`):**

Liest alle `<Trade>`-Elemente und mappt IBKR-Attribute auf interne Spaltennamen.

**Sonderfall CASH-Trades (FX):**

IBKR meldet einen Währungstausch (`assetCategory="CASH"`, Symbol `<Basis>.<Quote>`, z. B.
`EUR.USD`) als **einen** `<Trade>`. Daraus entstehen drei Zeilen — eine in `trades_fx`, zwei in
`trades_raw`:

```
trades_fx (1 Zeile je Tausch — Grundlage der Ansicht „FX-Trades“):
  baseCurrency/quoteCurrency  aus dem Symbol (EUR / USD)
  baseAmount                  = quantity  (Betrag in Basiswährung, Vorzeichen von IBKR)
  quoteAmount                 = proceeds  (Betrag in Gegenwährung)
  fxRate                      = tradePrice
  commission                  = ibCommission

trades_raw (2 Zeilen, gemeinsame linkID — „von“ und „nach“):
  Zeile „von“:  quantity = 1, currency = Basis, tradePrice = Kurs,   netCash = Basisbetrag,
                ibCommission = Kommission
  Zeile „nach“: quantity = 2, currency = Quote, tradePrice = 1/Kurs, netCash = Gegenbetrag,
                ibCommission = 0
```

`quantity` ist hier **keine Menge**, sondern nur die Kennung 1 = „von“, 2 = „nach“. Beispiel
aus echten Daten: EUR → USD zum Kurs 1,1686 ergibt in `trades_raw` die Zeilen
`(quantity 1, EUR, 1,1686, netCash −498,30)` und `(quantity 2, USD, 0,8557, netCash +582,31)`,
in `trades_fx` eine Zeile `EUR/USD, −498,30 / +582,31, Kurs 1,1686`. Ein FIFO-Matching findet
für FX **nicht** statt (siehe § 6.2, Fall 0). Die Umrechnung von Trades in Euro hängt nicht an
diesen Zeilen, sondern am `fxRateToBase`, das IBKR bei jedem Trade mitliefert. Die so
mitgeführten EUR-Werte zeigt die Weboberfläche derzeit nur auf den Detailseiten geschlossener
Trades neben dem USD-Wert (siehe § 11, Punkt H).

**Kein Forex-Trading:** Erfasst wird nur der Umtausch als solcher (z. B. EUR → USD für den
Aktienhandel). Devisenhandel als Strategie — Währungspositionen mit Gewinn/Verlust aus
Kursbewegungen — ist nicht umgesetzt: keine Tranchen, kein P&L, keine Kampagnen für `CASH`.

**OptionEAE-Extraktion (`extract_optioneae_for_db`):**

| `transactionType` | Bedeutung |
|---|---|
| `Expiration` | Option verfallen (wertlos) |
| `Exercise` | Option ausgeübt (durch Holder) |
| `Assignment` | Option zugewiesen (durch Writer) |
| `Cash Settlement` | Barzahlung statt Delivery (z.B. SPX, XSP) |

**CorporateActions (`extract_corporateaction_for_db`):**

| IBKR-Type | Bedeutung |
|---|---|
| `RS` | Reverse Split |
| `SS` | Stock Split (Forward) |
| `FS` | Forward Split |
| `DI` | Dividende |
| `TC` | Takeover / Merger |

### 5.4 Options-Strategie-Erkennung: `option_strategies.py`

IBKR liefert in den FlexQuery-Daten **keine Information über synthetische Produkte** wie Spreads oder andere Multi-Leg-Konstrukte — jedes Leg erscheint als eigenständiger, isolierter Trade ohne Verweis auf eine übergeordnete Strategie. Das System muss daher **heuristisch** erkennen, welche Einzeltrades zusammengehören.

`detect_strategies()` läuft beim Import je FlexStatement (also je Handelstag), nachdem
Teilausführungen zusammengefasst sind, und betrachtet nur echte Börsen-Trades
(`transactionType="ExchTrade"`; BookTrades aus Verfall/Zuteilung nie). Zwei Gruppierungen
werden nacheinander angewendet:

#### Methode 1: ibOrderID-Gruppierung (primär)
```
IBKR vergibt allen Legs einer Combo-Order dieselbe ibOrderID.
→ Options-Trades mit gleicher ibOrderID (mind. 2) = Kandidat
```

#### Methode 2: 3-Sekunden-Raster (Fallback)
```
Für einzeln eingegebene Legs ohne gemeinsame ibOrderID:
→ übrige Options-Trades desselben Underlyings, deren dateTime in dasselbe
  feste 3-Sekunden-Raster fällt (dateTime abgerundet auf 3 s) = Kandidat
```
Das Raster ist fest, kein gleitendes Fenster: Legs um 10:00:02 und 10:00:04 liegen in
verschiedenen Rastern (10:00:00 und 10:00:03) und werden **nicht** zusammengefasst.

**Klassifizierung:** Je Kandidat werden die Legs nach Strike/Typ/Verfall zusammengefasst
(Mengen summiert) und nach Anzahl der Legs eingeordnet. Nur wenn ein Name passt, bekommen alle
Legs dieselbe `opt_strategyID` (UUID), `opt_strategyName` und `opt_strategy=1`; sonst bleiben
sie Einzeloptionen.

| Name | Legs | Bedingung im Code |
|---|---|---|
| Bull Put Spread | 2 | Puts, gleicher Verfall, gleiche Menge, entgegengesetzt; höherer Strike short |
| Bear Put Spread | 2 | wie oben, höherer Strike long |
| Bear Call Spread | 2 | Calls, gleicher Verfall, gleiche Menge, entgegengesetzt; tieferer Strike short |
| Bull Call Spread | 2 | wie oben, tieferer Strike long |
| Calendar Spread | 2 | gleicher Typ und Strike, verschiedener Verfall, entgegengesetzt |
| Diagonal Spread | 2 | gleicher Typ, verschiedener Strike und Verfall, entgegengesetzt |
| Straddle | 2 | Call + Put, gleicher Strike und Verfall, gleiche Richtung |
| Strangle | 2 | Call + Put, verschiedener Strike, gleicher Verfall, gleiche Richtung |
| Call / Put Butterfly | 3 | ein Typ, ein Verfall, Mengen 1 : 2 : 1, Summe 0 |
| Iron Condor | 4 | 2 Calls + 2 Puts, ein Verfall, Calls und Puts heben sich je auf |

Nicht erkannt (bleiben Einzeloptionen): ungleiche Mengen bei 2 Legs (Ratio Spreads), mehr als
4 Legs, Legs an verschiedenen Tagen.

**Was mit dem Namen passiert:** `trades_raw` speichert ihn an jedem Leg. `trades_open` übernimmt
ihn beim Eröffnen, `trades_close` übernimmt ihn **von der Eröffnung** — die Spreads-Ansichten in
TradingJournal gruppieren `trades_close` nach dieser `opt_strategyID`. Die Kampagne hängt
unabhängig davon am Underlying (§ 6.3).

**Grenzen (gegen Code und Echtdaten geprüft):**

- **Schließende Combo-Orders bekommen einen eigenen, „umgekehrten“ Namen.** Die Erkennung kennt
  keine Eröffnung/Schließung: Wer einen Bull Put Spread per Combo-Order zurückkauft, erzeugt in
  `trades_raw` einen „Bear Put Spread“ (in einem Konto der Echtdaten sind alle 32 „Bear Put
  Spreads“ und alle 10 „Bull Call Spreads“ solche Schließungen). Auswirkung nur auf die Ansicht *Raw Data* —
  `trades_close` und die Spreads-Auswertung verwenden die Strategie der Eröffnung.
- **Rolls werden als Spread erkannt.** Ein Roll als Combo-Order (alte Option zurückkaufen, neue
  verkaufen) sieht aus wie ein Calendar- oder Diagonal-Spread. Die neu eröffnete Option trägt
  dann diesen Namen und erscheint später als „Spread“ mit nur einem Leg (PAPER: 2 Diagonal
  Spreads, außerdem je ein bis drei gemischte Fälle in zwei weiteren Konten).
- **Iron Butterfly** (Short Call und Short Put am selben Strike) erfüllt die Iron-Condor-Regel
  und heißt deshalb „Iron Condor“; die Reihenfolge der Strikes wird nicht geprüft.

### 5.5 Verfall, Ausübung, Zuteilung: `book_trades.py`

Schließt IBKR eine Option automatisch (Verfall, Ausübung, Zuteilung, Barausgleich), stehen im
XML zwei Dinge: der **BookTrade** im `Trades`-Block (`transactionType="BookTrade"`), der die
Option ausbucht, und das **OptionEAE**-Ereignis, das den Grund nennt. Bei einer Zuteilung oder
Ausübung mit Aktienlieferung kommt ein dritter Eintrag dazu: der **Aktien-Trade** zum Strike, als
eigener Eintrag im `Trades`-Block. `flex_parser.py` trennt die BookTrades ab und gibt sie mit den
Options-EAE (`assetCategory="OPT"`) an `handle_booktrades()`.

**Schritt 1 — Status am Options-BookTrade (Parser):**

```
Assignment / Exercise / Expiration:
  BookTrade.tradeID == OptionEAE.tradeID  → Ereignistyp übernehmen
Cash Settlement (eigene tradeID ohne Bezug zum BookTrade):
  BookTrade.conid == OptionEAE.conid und Datum höchstens 1 Tag auseinander

Status (Spalte trades_raw.status):
  Assignment oder Exercise   → "Assigned"   (auch die Ausübung — einen eigenen
                                             Status "Exercised" gibt es nicht)
  zusätzlich Cash Settlement → "CashSettled", proceeds = Barausgleich
                               (SPX: Exercise/Assignment + Cash Settlement)
  Expiration                 → "Expired"
  nur Cash Settlement        → "CashSettled" + Warnung (sollte nicht vorkommen)
```

**Schritt 2 — Option mit Aktie verknüpfen (Parser, nur bei *Assignment*):**

```
Voraussetzung: OptionEAE hat underlyingConid (fehlt beim Barausgleich)
1. linkID = neue UUID → auf den Options-BookTrade
2. Aktien-Trade suchen:
     assetCategory = "STK"
     conid         = underlyingConid der Option
     |quantity|    = |Kontrakte| × multiplier   (z. B. 1 × 100 = 100 Aktien)
     noch nicht mit einer anderen Zuteilung verknüpft
   bei mehreren Treffern: der zeitlich nächste zum EAE-Datum
3. Treffer → gleiche linkID + status "Assigned" auf den Aktien-Trade
   kein Treffer → Logzeile "Kein passender Stock-Trade gefunden", Option behält linkID
```

Beide Einträge landen so in `trades_raw` mit derselben `linkID`.

**Schritt 3 — Verarbeitung (`process_ibkr_trades.py`):** Der Options-BookTrade schließt die
offene Options-Tranche (FIFO, § 6.2). In `trades_close` werden `status` und `closedBy` gesetzt
(`Assigned` → `ASSIGNMENT`, `Expired`/`CashSettled` → `EXPIRY`); die `linkID` kommt dabei vom
schließenden BookTrade, nicht von der Eröffnung (die nie eine hat). Im Fall 2c (exakter
Gegenabschluss) schreibt das Ledger `OPTION_EXERCISE` bzw. `OPTION_EXPIRATION` /
`CASH_SETTLEMENT`. Bei `OPTION_EXERCISE` merkt sich der Tracker die `linkID` als
`pending_link_id` am Underlying; eröffnet der nächste Aktien-Trade dieses Underlyings eine
Position (Fall 1), bekommt sein Ledger-Eintrag diese `linkID`. Schließt der Aktien-Trade dagegen
eine bestehende Position (z. B. Covered Call zugeteilt → Aktien gehen weg), trägt er die
`linkID` aus Schritt 2 direkt in seinen `trades_close`-Eintrag. Option und Aktie landen in
derselben Kampagne, weil die Kampagne am Underlying hängt (§ 6.3).

**Nutzung in TradingJournal:** `SpreadsList`/`SpreadDetail` addieren das Ergebnis der über
`linkID` verknüpften Aktien-Trades zum Spread-Ergebnis (sonst wäre ein zugeteilter Bull Put
Spread zu optimistisch, weil der Verlust aus der Aktienzuteilung fehlt). Die Detailseiten offener
und geschlossener Trades zeigen verknüpfte Trades mit gleicher `linkID` an.

**Grenzen (gegen Code und Echtdaten geprüft):**

- **Ausübung eigener Optionen** (*Exercise*): Der Parser vergibt keine `linkID`, der Aktien-Trade
  wird nicht gesucht. Nur im Fall 2c erzeugt die Verarbeitung eine `linkID` für den Ledger-Eintrag
  des nächsten eröffnenden Aktien-Trades; in `trades_close`/`trades_open` bleibt sie leer.
- **Teilschließungen** (Fall 2a/2b, z. B. 1 von 2 Kontrakten zugeteilt oder eine in zwei
  Tranchen eröffnete Option auf einmal verfallen): Der Status in `trades_close` wird auf `Closed`
  überschrieben, das Ledger schreibt eine normale Schließung statt `OPTION_EXERCISE` /
  `OPTION_EXPIRATION`, und es gibt keine `pending_link_id`. `closedBy` bleibt richtig
  (`ASSIGNMENT`/`EXPIRY`). In den Echtdaten kommt das bisher nur bei Verfall vor (8 Einträge
  `status=Closed, closedBy=EXPIRY` über alle Environments).
- **Ohne Aktien-Gegenstück** (z. B. Barausgleich) bleibt die `linkID` des Options-Eintrags ohne
  Partner. Ältere Datenbestände lassen sich mit `dev/migrate_backfill_assignment_linkid.py`
  nachträglich verknüpfen (idempotent).

### 5.6 Duplikat-Schutz: Checksums

**Konzept:** Jeder Trade erhält vor dem Insert einen MD5-Hash:

```python
checksum = MD5(tradeID + dateTime + symbol + quantity + price)
```

**Ablauf:**
```
1. Berechne Checksums für alle neuen Trades
2. SELECT checksums FROM trades_raw WHERE checksum IN (...)
3. Filtere bekannte Checksums heraus
4. INSERT nur wirklich neue Trades
```

**Vorteil:** Dasselbe XML kann mehrfach importiert werden (z.B. nach Neustart) — keine Duplikate.

---

## 6. Phase 2 — Processing (trades_raw → Endtabellen)

### 6.1 Einstiegspunkt: `process_ibkr_trades.py`

```python
# Hole alle unverarbeiteten Trades (processed=0), chronologisch sortiert
trades = repo.get_unprocessed_trades(environment)

for trade in trades:
    process_raw_trade(logger, trade, repo, tracker, campaign_id)
    repo.mark_trade_processed("trades_raw", trade["id"])
```

**Schlüsselprinzip:** Trades werden in **Zeitreihenfolge** verarbeitet. FIFO ist nur korrekt, wenn ältere Positionen zuerst geschlossen werden.

**Reihenfolge-Garantie — und ihre Grenze:** Sortiert wird nur die aktuelle Menge
`trades_raw.processed=0` (`DBAccess.get_all_raw_trades`: `ORDER BY dateTime ASC, symbol ASC`).
Innerhalb eines Laufs sind Dateireihenfolge, Quelle (`incoming_mail`/`incoming_api`) und
Mehrfachlieferungen (Checksum-Dedup beim Import) deshalb irrelevant. Bereits verarbeitete Trades
werden aber nicht neu einsortiert, und es gibt **keinen Guard** gegen nachträglich ankommende
ältere Trades: Ein Trade mit `dateTime` vor dem jüngsten verarbeiteten Trade desselben
Environments läuft gegen den aktuellen `trades_open`-/Tracker-Stand. Beispiel: Kauf 02.03. kommt
nach dem bereits verarbeiteten Verkauf 10.03. → der Verkauf hat zuvor ohne Bestand per Fall 1
eine Short-Tranche eröffnet, der Kauf schließt sie (Fall 2c) — Bestand 0, aber Richtung,
`dateTimeOpen`/`dateTimeClose` und Kampagnenzuordnung falsch. Im Regelbetrieb tritt das nicht auf
(jeder Bericht überlappt die letzten n Tage, ein Trade kommt im ersten Bericht nach dem
Handelstag), relevant ist es beim Nachholen von Altdaten nach dem ersten produktiven Lauf oder bei
lange liegengebliebenen Dateien (z. B. unbekannte `accountId`, später in `accounts.toml`
ergänzt). Kampagnen-Ablauf (`close_old_pending_campaigns`) und PENDING→CLOSED richten sich
dagegen nach Trade-Datum (`reference_date` = erster Trade des Laufs), nicht nach `now()`.
**Korrektur:** Neuaufbau per `reset_IBKR_DB.py` + `--from-summary` (Summary ist nach `fromDate`
sortiert). `reset_IBKR_DB.py` legt dabei u. a. auch `trade_planner`, `trade_planner_legs` und
`account_snapshots` neu an — Trade-Log-Einträge vorher sichern, Snapshots durch Zurücklegen der
CSVs aus `C:\Trade_CSV\incoming\<user>\processed\` neu importieren. `account_snapshots` selbst sind
reihenfolgeunabhängig (ein Datensatz je `snapshot_date`, Dedup).

### 6.2 FIFO-Matching: Die Fälle

IBKR-Vorzeichenkonvention:
- **BUY:** `netCash` negativ (Geld fließt raus)
- **SELL:** `netCash` positiv (Geld fließt rein)

```
Aktueller Bestand im Tracker: current_qty
Neuer Trade:                   new_qty (positiv = Long, negativ = Short)

FIFO-Queue: offene Tranchen in trades_open (processed=0) je Symbol/conid,
            ältester Eintrag zuerst (ORDER BY dateTime ASC)
```

Geschlossene Tranchen werden in `trades_open` nicht gelöscht, sondern auf `processed=1` gesetzt
(History). Wirklich offen ist nur, was `processed=0` hat.

#### Fall 0: CASH / FX-Trade
```
assetCategory = "CASH"   (die beiden „von“/„nach“-Zeilen aus § 5.3)
→ Keine Kampagne, kein FIFO, kein Eintrag in trades_open/trades_close
→ trades_raw markieren: processed=1
  (trades_fx wird bereits beim Import befüllt, nicht hier)
```

Im Code steht zusätzlich ein Zweig, der für die Zeile „von“ `FX_EXCHANGE_FROM_<Basis>` und für
„nach“ `FX_EXCHANGE_TO_<Quote>` ins Ledger schreiben würde — aber nur mit `campaign_id`. Da
CASH-Trades vor der Verarbeitung nie einer Kampagne zugeordnet werden (`campaign_id = None`),
läuft dieser Zweig derzeit nie; in den Echtdaten gibt es keinen einzigen `FX_*`-Ledger-Eintrag.

#### Fall 1: Gleiche Richtung (Positionsaufbau)
```
Bedingung: current_qty * new_qty > 0  ODER  current_qty = 0
           (Produkt > 0 ⇔ gleiches Vorzeichen ⇔ gleiche Richtung;
            eine Summe würde nicht funktionieren: 100 + (−50) = 50 > 0)

Beispiel: Bestand = 100 AAPL, neuer Trade = BUY 50 AAPL
          → 100 × 50 > 0, Bestand wird 150
          Bestand = −100 AAPL (short), neuer Trade = SELL 50 AAPL
          → (−100) × (−50) > 0, Short wird −150
          Bestand = 100 AAPL, neuer Trade = SELL 50 AAPL
          → 100 × (−50) < 0 → kein Fall 1, sondern Fall 2a (Teilschließung)

Aktion: INSERT trades_open (status=OPEN)
        Kampagne: TRADE_OPEN im Ledger
```

#### Fall 2c: Exakter Gegenabschluss
```
Bedingung: abs(open_tranche.qty) == abs(new_qty), entgegengesetzt

Beispiel: Bestand = 100 AAPL (1 Tranche), neuer Trade = SELL 100 AAPL
          → Position wird 0

Aktion: INSERT trades_close (status=Closed)
        trades_open markieren: processed=1
        Kampagne: TRADE_CLOSE_FULL → Status PENDING
```

#### Fall 2a: Teilabschluss
```
Bedingung: abs(open_tranche.qty) > abs(new_qty), entgegengesetzt

Beispiel: Bestand = 100 AAPL (1 Tranche), neuer Trade = SELL 60 AAPL
          → 60 AAPL geschlossen, 40 AAPL bleiben offen

Aktion: INSERT trades_close (60 Stück, status=Closed)
        alte Tranche in trades_open markieren: processed=1
        INSERT trades_open: neue Zeile mit den 40 Reststück (status=SPLIT_REST),
          netCash/proceeds/ibCommission anteilig (40/100)
        Kampagne: TRADE_CLOSE_PARTIAL im Ledger
```

**Schlüsselkonzept: Ratio-Skalierung**
```python
ratio = close_qty / open_qty  # z.B. 60/100 = 0.6

# Die Open-Werte werden auf den geschlossenen Anteil skaliert:
netCash_open_anteil    = open_trade.netCash      * ratio
proceeds_open_anteil   = open_trade.proceeds     * ratio
commission_open_anteil = open_trade.ibCommission * ratio
# → ROI und P&L sind korrekt trotz Teilabschluss (Details: § 6.4)
```

#### Fall 2b: Neuer Trade größer als die Tranche
```
Bedingung: abs(new_qty) > abs(open_tranche.qty), entgegengesetzt

Beispiel: Tranchen A = 100 AAPL, B = 50 AAPL, neuer Trade = SELL 120 AAPL
          → A komplett geschlossen, die übrigen 20 laufen weiter gegen B (dort Fall 2a)

Aktion: INSERT trades_close (Tranche komplett, status=Closed)
        Tranche in trades_open markieren: processed=1
        Restmenge des neuen Trades (anteilig netCash/proceeds/ibCommission)
          → nächste Tranche der Schleife
        Kampagne: TRADE_CLOSE_FULL im Ledger je Tranche
```

#### Umkehrung (Reversal): Restmenge nach allen Tranchen
```
Bedingung: nach der Schleife über alle Tranchen ist remaining_qty != 0

Beispiel: Bestand = 100 AAPL (mehrere Tranchen), neuer Trade = SELL 250 AAPL
          → Alle Tranchen schließen (FIFO, Fälle 2b/2c), 150 AAPL werden Short

Aktion: Restmenge → INSERT trades_open (status=REV_OPEN)
        Kampagne: TRADE_REVERSAL_OPEN im Ledger, gleiche Kampagne
          (die Position war nie flat, daher keine neue Kampagne)
```

#### Fall SPLIT: Corporate Action (Aktiensplit)

**Woher die Daten kommen:** Aus dem Abschnitt *Kapitalmaßnahmen* der Flex Query
(`<CorporateAction>`, Option *Detail*). `extract_corporateaction_for_db()` übernimmt jede
Kapitalmaßnahme als Zeile in `trades_raw` (`source="split"`, `dateTime` = `reportDate`) und
setzt `is_split=1` für die Typen `RS` (Reverse Split), `FS` (Forward Split) und `SS` (Split) —
die Liste steht an einer Stelle in `src/utils/corporate_utils.py`. IBKR liefert einen Split als
**Paar mit derselben `actionID`**: die alten Aktien gehen raus (negative Menge, Symbol meist mit
Endung `.OLD`), die neuen kommen rein (positive Menge, neues Symbol). `sort_corporate_actions()`
ordnet die Paare (alter Teil zuerst).

**Verarbeitung** (`process_ibkr_trades.py`, vor der Kampagnenlogik — Split-Zeilen lösen keinen
PENDING/ACTIVE-Wechsel aus):

```
1. _handle_split_trade(): Zeilen je actionID puffern
     erster Teil  → warten, als verarbeitet markieren
     zweiter Teil → Faktor = |Menge neu| / |Menge alt|, Symbol = neues Symbol
2. process_stock_split(): alle offenen Tranchen des Symbols (trades_open, processed=0)
     quantity   = quantity × Faktor
     tradePrice = tradePrice / Faktor          (Einstand gesamt bleibt gleich)
     Menge 0    → Tranche geschlossen (processed=1), nicht als 0-Menge stehen lassen
     Ledger     → STOCK_SPLIT, inventory_delta = neue − alte Menge, kein Cash, kein P&L
3. Tracker: Bestand der Kampagne × Faktor, danach Flat-Check (Bestand 0 → PENDING)
```

Kein Cash, kein Gewinn/Verlust: Ein Split ändert nur Stückzahl und Preis je Aktie. Spätere
Trades finden die Tranchen über das Symbol; ändert IBKR beim Split die `conid`, greift der
Fallback in `get_open_trades()` nicht ein, weil das Symbol gleich bleibt.

**Beispiele aus echten Daten** (beide Reverse Splits):

| Symbol | Datum | alt → neu | Faktor | Ledger `inventory_delta` |
|---|---|---|---|---|
| CYN | 18.02.2025 | 4.152 → 27,68 | ≈ 0,00667 (1:150) | −4.124,32 |
| APDN | 14.03.2025 | 1.500 → 30 | 0,02 (1:50) | −1.470 |

Die neue Menge kann krumm werden (27,68 CYN-Aktien) — sie wird so übernommen, wie IBKR sie
liefert.

**Grenzen (gegen Code und Echtdaten geprüft):**

- **Optionen auf die gesplittete Aktie** werden erkannt (`is_split=1`), aber offene
  Options-Tranchen werden nicht umgestellt: `process_stock_split()` sucht nach dem *neuen*
  Options-Symbol, die Tranche steht aber unter dem alten. Bisher nur einmal vorgekommen
  (PAPER, TQQQ-Forward-Split 20.11.2025) — ohne offene Position, daher ohne Auswirkung.
- **Mehr als zwei Zeilen je `actionID`** (z. B. mehrere Options-Strikes in einer
  Kapitalmaßnahme) passen nicht ins Paar-Schema; ab der dritten Zeile beginnt ein neues Paar.
- Der zweite Teil des Paares wird im selben Lauf nicht als verarbeitet markiert; der nächste
  Lauf puffert ihn allein („warte auf zweiten Teil“) und markiert ihn dann — ohne
  Auswirkung auf die Daten.
- Der Ledger-Eintrag `STOCK_SPLIT` trägt das **Eröffnungsdatum der Tranche**, nicht das
  Split-Datum (CYN: Ledger 10.02.2025, Split 18.02.2025).
- **Andere Kapitalmaßnahmen** (Fusion, Spin-off, Symbolwechsel) bekommen `is_split=0` und
  würden wie normale Trades (Preis 0) durch die FIFO-Logik laufen — eine eigene Behandlung gibt
  es nicht. In den Echtdaten bisher nicht vorgekommen.

### 6.3 Kampagnen-Lebenszyklus: `inventory_tracker.py`

**Ursprung:** Die Kampagne wurde konzipiert, um die **Wheel-Strategie** (auch "Bonus-Strategie") vollständig zu dokumentieren. Bei der Wheel-Strategie werden auf dasselbe Underlying zyklisch Cash-Secured Puts und Covered Calls verkauft — oft über Wochen oder Monate. Eine Kampagne bildet genau diesen Zyklus ab: vom ersten Put bis zur letzten Aktienlieferung oder Ausübung.

Die **10-Tage-Wartezeit** (PENDING-Phase) ist ebenfalls auf die Wheel-Strategie abgestimmt: Nach dem scheinbaren Ende eines Zyklus (Position = 0) kann innerhalb weniger Tage ein neuer Put auf dasselbe Underlying eröffnet werden. Die PENDING-Phase verhindert, dass dafür sofort eine neue Kampagne angelegt wird — stattdessen wird der Trade in die bestehende aufgenommen, solange das Zeitfenster noch offen ist. Die Frist ist per `.env` einstellbar (`MAX_GAP_DAYS`, Kalendertage, Standard 10, empfohlen 7–14; gelesen in `src/config.py`, ungültige Werte brechen ab). Sie gilt nur für künftige Verarbeitung — bestehende Kampagnen ändern sich erst nach einem Neuaufbau.

**Konzept:** Eine *Kampagne* fasst alle Trades zu einem Symbol in einem zusammenhängenden Zeitraum zusammen.

```
AKTIVE Kampagne:
  ├── Symbol: AAPL
  ├── Start: 2025-01-10
  ├── Bestand: 150 Aktien + 2 Calls
  ├── Status: ACTIVE
  └── Ledger: TRADE_OPEN (x3), TRADE_CLOSE_PARTIAL (x1)

Nach vollständigem Schließen:
  └── Status: PENDING (Wartezeit: 10 Tage)
      → Sicherheitsnetz: Falls IBKR nachträgliche Korrekturtrades sendet

Nach 10 Tagen ohne Aktivität:
  └── Status: CLOSED
      ├── closed_at: 2025-02-05
      └── Finale P&L berechnet
```

**Ledger-Aktionen (`LedgerAction`-Enum in `src/trade_enums.py`):**

Seit 2026-05 werden **feingranulare Actions** geschrieben — statt generischem `TRADE_OPEN` / `TRADE_CLOSE_*` benennt die Action Instrument, Richtung und Abschlussart. Die Zuordnung erfolgt über `_open_action()` / `_close_action()` in `process_ibkr_trades.py`.

| Gruppe | Actions | Auslöser |
|---|---|---|
| Aktien: Eröffnung | `STK_BUY`, `STK_SELL` | Fall 1 (Long- bzw. Short-Einstieg) |
| Aktien: Schließung | `STK_SELL_CLOSE`, `STK_BUY_CLOSE`, `STK_SELL_PARTIAL`, `STK_BUY_PARTIAL` | Fall 2c (voll) bzw. 2a (teilweise) |
| Optionen: Eröffnung | `OPT_PUT_SELL`, `OPT_PUT_BUY`, `OPT_CALL_SELL`, `OPT_CALL_BUY` | Fall 1 |
| Optionen: Schließung | `OPT_PUT_BUY_CLOSE`, `OPT_PUT_SELL_CLOSE`, `OPT_CALL_BUY_CLOSE`, `OPT_CALL_SELL_CLOSE` + `*_PARTIAL`-Varianten | Fall 2c bzw. 2a |
| Options-Events | `OPTION_EXPIRATION`, `OPTION_EXERCISE`, `CASH_SETTLEMENT` | OptionEAE (Verfall / Ausübung+Assignment / Barausgleich) |
| Sonstiges | `TRADE_REVERSAL_OPEN`, `STOCK_SPLIT` | Fall 2b Remainder / CorporateAction |
| (vorgesehen, derzeit nie geschrieben) | `FX_EXCHANGE_FROM_<Währung>`, `FX_EXCHANGE_TO_<Währung>` | CASH-Trade mit Kampagne — siehe Fall 0 |

**Hinweis:** Die generischen Bezeichnungen `TRADE_OPEN`, `TRADE_CLOSE_FULL`, `TRADE_CLOSE_PARTIAL` in den Fallbeschreibungen oben (Abschnitt 6.2) stehen stellvertretend für die jeweilige feingranulare Action. Ältere Datenbestände können noch die generischen Actions enthalten; TradingJournal kennt beide Varianten, ein Neuaufbau per Summary-Re-Import schreibt die feingranularen.

### 6.4 Schema-Validierung: `open_trade.py` / `closed_trade.py`

**Warum Schemas?**

Ohne explizite Validierung können falsche Datentypen, fehlende Felder oder falsche Vorzeichen unbemerkt in die Datenbank gelangen und P&L-Berechnungen verfälschen.

**`OpenTradeSchema.validate()`:**
```python
REQUIRED_FIELDS = ["quantity", "tradePrice", "netCash", "status", ...]
FIELD_TYPES = {"quantity": Decimal, "tradePrice": Decimal, ...}

# Status-Validierung:
assert status in [TradeStatus.OPEN, TradeStatus.REV_OPEN, TradeStatus.SPLIT_REST]
```

**`to_closed_trade(open_trade, close_data, ratio)`** (Fall 2b/2c) und
**`partial_close_new_open(...)`** (Fall 2a):

Dies sind die **kritischsten Funktionen** im System. Sie erzeugen aus einer offenen Tranche und
dem schließenden Trade einen abgeschlossenen Trade (`trades_close`). Vereinfacht für
`to_closed_trade` — die offene Tranche wird hier immer vollständig geschlossen, skaliert wird nur
der Anteil des schließenden Trades (`ratio`):

```python
# Open-Seite (Tranche vollständig):
proceeds_open    = open_trade.proceeds
open_commission  = open_trade.ibCommission

# Close-Seite (nur der Anteil, der diese Tranche schließt):
proceeds_close   = close_data.proceeds     * ratio
close_commission = close_data.ibCommission * ratio

# P&L — BRUTTO, ohne Kommissionen:
profit     = proceeds_open + proceeds_close
profit_EUR = proceeds_open * fxRate_open + proceeds_close * fxRate_close

# Kommissionen separat (IBKR: negativ):
ibCommission = open_commission + close_commission
# Netto-P&L wird erst in der Anzeige gebildet: profit + ibCommission

# ROI in Prozent, Basis: eingesetztes Kapital (netCashOpen), Vorzeichen wie profit:
ROI = abs(profit / netCashOpen * 100)    # negativ, wenn profit < 0

# Haltezeit:
days_held, total_seconds, duration_text = calculate_hold_metrics(open_dt, close_dt)
```

Bei `partial_close_new_open` (Fall 2a) ist es umgekehrt: Der schließende Trade zählt vollständig,
die Open-Seite (`netCash`, `proceeds`, `ibCommission`) wird mit dem geschlossenen Anteil skaliert,
der Rest bleibt als `SPLIT_REST` offen.

**Warum `proceeds` statt `netCash`?** `proceeds` ist der reine Handelsbetrag ohne Kommission und
funktioniert für alle Abschlussarten — auch für Cash Settlement, bei dem `netCashClose` 0 ist,
`proceeds` aber den Barausgleich enthält. Alle P&L-Felder (`trades_close.profit`,
`campaign_ledger.realized_pnl`) sind deshalb **brutto**; die Kommission steht immer separat.

---

## 7. Kernkonzepte

### 7.1 Warum FIFO?

IBKR-Steuerberichte verwenden FIFO (First In, First Out) für Lot-Matching — das System bildet diese Logik nach, damit P&L-Berechnungen mit offiziellen IBKR-Berichten übereinstimmen. Die FIFO-Queue in `trades_open` ist nach `datetime` aufsteigend sortiert: älteste Tranche wird zuerst geschlossen.

**Einschränkung beim Automations-Trading (TAT):** Der automatisierte Trader (TAT) verwaltet intern seine eigene Lot-Zuordnung und schließt Positionen nicht zwingend in FIFO-Reihenfolge — insbesondere wenn mehrere offene Tranchen denselben Strike haben. In diesen Fällen kann die FIFO-Zuordnung dieses Systems von der TAT-internen Zuordnung abweichen: P&L und Haltezeit einzelner Trades werden dann anders berechnet als TAT es intern ausweist, auch wenn das Gesamtergebnis der Kampagne übereinstimmt.

### 7.2 Warum `Decimal` statt `float`?

```python
# float-Problem:
0.1 + 0.2 == 0.3  # → False (0.30000000000000004)

# In der Finanzwelt ist das inakzeptabel:
# Summe aus 1000 Trades kann um Cent-Beträge abweichen

# Lösung: Python Decimal (exakte Dezimalarithmetik)
from decimal import Decimal
to_decimal("0.1") + to_decimal("0.2") == Decimal("0.3")  # → True
```

`to_decimal()` aus `src/utils/div_utils.py` ist robust gegen verschiedene Eingabeformate:
- Strings mit Tausenderpunkten (`"1.234,56"`)
- Float (konvertiert über String, vermeidet Float-Fehler)
- None / leer → `Decimal(0)`

### 7.3 Multi-User / Multi-Environment

Das System verwaltet bis zu 5 Environments je User:

| Environment | Datenbank (Default) | Zweck |
|---|---|---|
| `money` | `ibkr_money` | Echtes Kapital |
| `paper` | `ibkr_paper` | Papierkonto / Simulation |
| `test` | `ibkr_test` | Entwicklung und Tests |
| `autom_money` | `ibkr_autom_money` | Automatisiertes Echtgeld |
| `autom_paper` | `ibkr_autom_paper` | Automatisiertes Paper |

DB-Namen können per `.env` überschrieben werden (`DB_NAME_MONEY`, `DB_NAME_PAPER`, …).

**Tabellen-Präfix** (`TABLE_PREFIX` aus `.env`):
```sql
-- User "dein_user" mit prefix "dein_user_":
SELECT * FROM dein_user_trades_raw;
SELECT * FROM dein_user_trading_campaigns;

-- User "zweiter_user" mit prefix "zweiter_user_":
SELECT * FROM zweiter_user_trades_raw;
```

Dies erlaubt mehrere User in **einer MySQL-Datenbank** ohne Kollisionen.

### 7.4 Transaktionen und Atomizität

Jeder Trade wird innerhalb einer Datenbank-Transaktion verarbeitet:

```python
with db.transaction():
    # Alle INSERTs/UPDATEs für einen Trade
    open_id = repo.insert_open_trade(trade_dict)
    repo.link_to_campaign_new(campaign_id, ...)
    repo.mark_trade_processed("trades_raw", raw_id)
    # Bei Fehler: Rollback → keine halbfertigen Zustände
```

**Ohne Transaktionen** könnten bei einem Absturz inkonsistente Zustände entstehen (z.B. `trades_close` vorhanden, aber `trades_open` nicht als processed markiert).

---

## 8. Datenbankstruktur

### 8.1 Tabellen-Übersicht

```
trades_raw        ← Rohdaten (temporärer Puffer)
    │
    ▼
trades_open       ← Aktive FIFO-Tranchen
    │
    ├──→ trades_close      ← Abgeschlossene Trades (P&L hier)
    │
    └──→ trading_campaigns ← Kampagne je Symbol
              │
              └──→ campaign_ledger  ← Vollständiger Audit-Trail

symbols           ← Instrument-Referenzdata (conid, ISIN, ...)
trades_fx         ← FX-Trades (separat)
account_snapshots ← Kontostand-Snapshots (aus CSV)
```

Dazu die Tabellen, die nur TradingJournal schreibt (Eingaben in der Oberfläche):

| Tabelle | Inhalt (UI) | Angelegt von |
|---|---|---|
| `trade_planner`, `trade_planner_legs` | **Log**: Plan, Begründung, Exit-Plan, Ergebnis je Eintrag bzw. dessen Legs; optional per `campaign_id` mit einer Kampagne verknüpft | `reset_IBKR_DB.py` (wird beim Neuaufbau mit geleert) |
| `psychology_rulesets`, `psychology_rules` | **Psychologie → Regelwerke** | `tools/maintenance/setup_psychology_tables.py` (nicht durch `reset_IBKR_DB.py` berührt) |
| `psychology_entries`, `psychology_compliance_results` | **Psychologie → Einträge**, Einhaltung je Regel und Eintrag | wie oben |

### 8.2 Schlüsseltabellen im Detail

Die folgenden Spaltenlisten sind auf die fachlich relevanten Felder gekürzt, aber
**wörtlich aus `TradingJournal-Weaver/sql/*.sql` übernommen** (keine erfundenen/veralteten Spalten) —
für die vollständige Liste inkl. Typen/Defaults ist `sql/*.sql` die Quelle der Wahrheit.

#### `trades_raw` — Rohdaten-Puffer
```sql
id, checksum,                         -- Eindeutigkeit
environment,                          -- Routing (accountId selbst wird nicht gespeichert,
                                       -- nur beim Import ausgewertet)
symbol, conid, assetCategory, buySell, -- Instrument
quantity, tradePrice, netCash,        -- Mengen/Preise
ibOrderID, tradeID,                   -- IBKR-Referenzen
opt_strategyID, opt_strategyName,     -- Strategie-Info
is_split, split_type,                 -- Corporate-Action-Kennzeichnung
source,                               -- Ursprungs-Elementtyp: trade | optioneae | split
processed,                            -- Status (0/1)
dateTime                              -- Zeitstempel
```

#### `trades_open` — Aktive Tranchen
```sql
id, symID,
symbol, conid, assetCategory,
quantity, tradePrice, netCash,        -- Einstiegswerte
ibCommission, fxRateToBase,
status,                               -- OPEN | REV_OPEN | SPLIT_REST
opt_strategyID, opt_strategyName, linkID,
environment, dateTime,
processed                             -- 0=offen, 1=geschlossen (History-Zeile, siehe § 6.1)
```
**Kein `campaign_id`** in dieser Tabelle — die Verknüpfung zur Kampagne läuft über
`campaign_ledger.source_table`/`source_id`, nicht über eine FK-Spalte hier.

#### `trades_close` — Abgeschlossene Trades
```sql
id, symID, symbol, conid,
-- Open-Seite:
tradeIDOpen, tradePriceOpen, dateTimeOpen, netCashOpen,
-- Close-Seite:
tradeIDClose, tradePriceClose, dateTimeClose, netCashClose,
quantity,                             -- geschlossene Menge (eine Spalte, kein Open/Close-Paar)
-- Ergebnis:
profit, profit_EUR, ROI,
daysHeld, durationStr,
ibCommission, ibCommission_EUR,
status,                               -- Closed | Expired | Assigned | CashSettled
closedBy,                             -- z.B. SELL / EXPIRY / ASSIGNMENT
opt_strategyID, opt_strategyName, linkID
```
Ebenfalls **kein `campaign_id`** — gleiches Prinzip wie bei `trades_open`.

#### `trading_campaigns` — Kampagnen
```sql
id, name, symbol, strategy, assetCategory,
status,                               -- ACTIVE | PENDING | CLOSED
start_date, end_date, closed_at,
environment
```
**Keine gespeicherten Aggregate** (`total_profit`, `total_commission`, `inventory`) — diese
Werte werden zur Laufzeit ermittelt: Bestand aus `trades_open`, P&L-Stand aus dem jeweils
letzten `cum_pnl`/`cum_commission`/`cum_premium`-Eintrag in `campaign_ledger` (§ 8.3).

#### `campaign_ledger` — Audit-Trail (ES-Lite)
```sql
id, campaign_id,
action,                               -- LedgerAction: STK_BUY | OPT_PUT_SELL | ... (s. 6.3)
inventory_delta,                      -- Bestandsänderung
netcash, proceeds, commission,        -- Cashflows dieser Zeile
realized_pnl,                         -- P&L dieses Events
cum_pnl,                              -- kumulierter P&L der Kampagne bis hier
cum_commission,                       -- kumulierte Kommissionen bis hier
cum_premium,                          -- kumulierte Erlöse bis hier
source_table, source_id,              -- Rückverweis (TRADES_OPEN / TRADES_CLOSE / TRADES_RAW)
dateTime
```

Die drei `cum_*`-Spalten ermöglichen Zeitreise-Abfragen ohne vollständigen Replay:
```sql
-- P&L-Stand der Kampagne am 15. März:
SELECT cum_pnl FROM dein_user_campaign_ledger
WHERE campaign_id = 42 AND dateTime <= '2025-03-15'
ORDER BY dateTime DESC, id DESC LIMIT 1;
```

#### `account_snapshots` — Kontostand-Snapshots (täglich)
```sql
id, snapshot_date, environment,
nav_prior, nav_current, nav_change, twrr,     -- Nettovermögenswert
starting_value, mtm_pnl, ending_value,        -- Veränderung des NAV
cash_eur, cash_usd,                           -- Cash-Positionen (siehe Limitierung unten!)
commissions_eur, forex_translation_pnl,
realized_pnl_eur, unrealized_pnl_eur,
mtd_pnl, ytd_pnl,
imported_at
```
Befüllt **ausschließlich** von `import_csv_snapshots.py` (`activity_csv_parser.py`,
`snapshot_csv`-Step, TWRR exakt von IBKR) aus dem **Kontoauszug (Activity Statement, CSV)**,
den IBKR nur per Mail zustellt — eine Abfrage per Web-API gibt es dafür nicht, und die
FlexQueries (Mail wie API) enthalten keine Snapshot-Sektionen. Bleibt die Mail an einem Tag
aus, fehlt der Snapshot dieses Tages.

**⚠️ Limitierung: fest auf EUR + USD verdrahtet, nicht generisch.**
Anders als bei Einzeltrades (`trades_raw.currency` ist freier Text, `trades_fx` speichert Basis-
und Gegenwährung je Tausch aus dem Symbol) ist die Cash-Position im
Portfolio-Snapshot **hartverdrahtet auf genau zwei Währungen**:

- Schema: `sql/account_snapshots.sql` hat feste Spalten `cash_eur` / `cash_usd`, keine generische Struktur.
- CSV-Import: `activity_csv_parser.py::_extract_cash()` ruft `find('Ending Cash', 'EUR')` und
  `find('Ending Cash', 'USD')` auf.

Hält das IBKR-Konto Cash in einer dritten Währung (z.B. GBP), wird dieser Betrag beim Snapshot-Import
**stillschweigend nicht erfasst** — kein Fehler, keine Warnung, der Wert fehlt einfach in
`account_snapshots`. Bewusste Vereinfachung für ein Konto, das nur in EUR (Basiswährung) und USD
(Handelswährung für US-Optionen/Aktien) bewegt wird. Für weitere Cash-Währungen braucht es eine
bewusste Erweiterung (neue Spalte(n) + Parser-Anpassung).

### 8.3 Running Balance — ES-Lite-Upgrade

Das `campaign_ledger` wurde um drei kumulierte Salden erweitert, die bei jedem INSERT automatisch berechnet und mitgeschrieben werden (`inventory_tracker.py → _get_running_totals()`):

| Spalte | Berechnung | Nutzen |
|---|---|---|
| `cum_pnl` | SUM(realized_pnl) je Kampagne | historischer P&L-Stand |
| `cum_commission` | SUM(commission) je Kampagne | Gesamtkosten-Verlauf |
| `cum_premium` | SUM(proceeds) je Kampagne | Prämieneinnahmen (Wheel-Tracking) |

Bestehende Daten wurden per `dev/migrate_running_balance.py` nachbefüllt (Window-Functions,
liegt seit einer Aufräum-Aktion in `dev/` statt `src/` — reine Einmal-Migrationsskripte, auf
einer frischen Installation nie gebraucht):
```bash
python -m dev.migrate_running_balance                  # alle Environments
python -m dev.migrate_running_balance money dein_user_      # einzelnes Target
```

---

## 9. Konfiguration & Multi-User

### 9.1 Konfigurationsdateien

| Datei | Zweck | Versioniert? |
|---|---|---|
| `.env` | Secrets (DB-Passwort, API-Keys) | **Nein** (gitignore, siehe `.env.example`) |
| `users.toml` | Zentrale User↔Prefix-Registry (einzige Quelle für z.B. `dein_user` → `dein_user_`) | **Nein** (gitignore, siehe `users.toml.example`) — enthält die echten Benutzernamen |
| `config.py` | DB-Konfiguration, lädt Account-Mapping aus `accounts.toml` (`get_account_config()`) | Ja |
| `accounts.toml` | Account-Mapping (accountId-Suffix → User/Environment, ohne Prefix) | **Nein** (gitignore, siehe `accounts.toml.example`) — enthält reale Kontodaten |
| `pipeline.toml` | Pipeline-Schritte, aktive User dieser Maschine | **Nein** (gitignore, siehe `pipeline.toml.example`) — maschinenspezifisch: jede Maschine verarbeitet nur die dort tatsächlich per `reset_IBKR_DB.py` initialisierten User/Environments |
| `CLAUDE.md` | Entwickler-Dokumentation | Ja |

### 9.2 `.env`-Struktur (Auszug)
```ini
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASS=...
DEFAULT_USER=dein_user
# Alternative/Override statt DEFAULT_USER: TABLE_PREFIX=dein_user_ direkt

IMAP_USERNAME=deine@email.at
IMAP_PASSWORD=...
IMAP_SERVER=imap.gmx.com

IBKR_FLEX_QUERIES=TOKEN1:111111,TOKEN1:222222
```
(vollständige Variablenliste inkl. `DB_NAME_*`-Overrides: siehe `.env.example`, § 4 oben
für die Mail-/API-spezifischen Variablen im Detail)

### 9.3 DB-Engine-Pattern (`src/config.py`)

```python
from src.config import get_engine

# Environment bestimmt Datenbank-Name (aus DB_MAP + .env):
engine = get_engine("money")
# → mysql+pymysql://user:pass@localhost:3306/ibkr_money
```

MySQL-Modus für Windows 11 Kompatibilität — wird bei jeder Verbindung gesetzt:
```python
# Verhindert MySQL-Fehler bei NULL-Datumswerten (Win11 ist strenger als Win10)
SET SESSION sql_mode='NO_ZERO_IN_DATE,NO_ZERO_DATE,NO_ENGINE_SUBSTITUTION'
```

### 9.4 Zusammenspiel `.env` / `accounts.toml` / `pipeline.toml`

Alle drei sind gitignored und maschinen-/personenspezifisch (im Gegensatz zum versionierten
`users.toml`), haben aber unterschiedliche Aufgaben und greifen an unterschiedlichen Stellen
im Ablauf:

```
.env              → WER bin ich (DB-Zugang, Mail-/API-Zugang, optional DEFAULT_USER)
accounts.toml     → WEM gehört diese XML-Datei (accountId → User + Environment)
pipeline.toml     → WAS läuft auf DIESER Maschine (welche User/Environments werden verarbeitet)
```

**Ablauf beim Import einer neuen FlexQuery-XML:**

1. `.env` liefert die DB-Zugangsdaten für die Verbindung selbst — unabhängig davon, welchem
   User/Environment die Datei am Ende zugeordnet wird.
2. `import_ibkr_trades.py` liest die `accountId` aus dem `<FlexStatement>` der XML und schlägt
   sie in `accounts.toml` nach (§ 5.1) → ergibt User (z.B. `dein_user`) + Environment
   (z.B. `money`). Der Tabellen-Prefix selbst steht nicht in `accounts.toml`, sondern wird
   erst zur Laufzeit aus `users.toml` aufgelöst (`get_account_config()`) — `accounts.toml`
   kennt also nur den User-*Namen*, nicht das Prefix.
3. Im Auto-Modus (kein CLI-Override) ist dieses Routing für den `import`-Step vollständig
   unabhängig von `pipeline.toml` — jede Datei landet dort, wohin ihre `accountId` zeigt,
   auch wenn dieser User/dieses Environment auf der aktuellen Maschine gar nicht in
   `pipeline.toml` eingetragen ist.
4. `pipeline.toml` wirkt erst beim `process`-Step (und bei `run_pipeline.py` generell für
   die Auswahl, welche User×Environment-Kombinationen ein Lauf überhaupt anfasst, § 3.2):
   nur wer hier eingetragen ist, wird verarbeitet — Daten für einen User, dessen Tabellen auf
   dieser Maschine nie per `reset_IBKR_DB.py` angelegt wurden, blieben sonst mit
   "Tabelle nicht gefunden" hängen.

**Praktische Konsequenz:** Ein neues IBKR-Konto anzulegen heißt **immer zwei Schritte**:
`accounts.toml` (Routing: welcher User/welches Environment) **und**, falls es sich um einen
komplett neuen User handelt, zusätzlich `users.toml` (Prefix) — sonst bricht `get_account_config()`
mit einer Meldung ab (fehlender User in `users.toml`), statt ohne Prefix weiterzuarbeiten. `pipeline.toml` muss nur ergänzt werden,
wenn diese Maschine den neuen User/das neue Environment auch tatsächlich lokal verarbeiten soll.

### 9.5 Konkretes Beispiel

Fiktives Setup: **Anna** nutzt die App allein, auf einem Rechner, mit einem Live-Konto
und einem Paper-Konto. So sehen ihre drei Dateien aus:

```ini
# .env — WER bin ich (DB-Zugang)
DB_USER=root
DB_PASS=geheim123
DEFAULT_USER=anna
```

```toml
# users.toml (lokal) — Anna → Prefix
[anna]
prefix = "anna_"
```

```toml
# accounts.toml — welches IBKR-Konto gehört zu welchem User/Environment
[4321]
user = "anna"
environment = "money"

[8765]
user = "anna"
environment = "paper"
```

```toml
# pipeline.toml — was verarbeitet DIESER Rechner
[users.anna]
environments = ["money", "paper"]
```

**Was passiert, wenn eine neue FlexQuery-XML von Annas Live-Konto ankommt** (`accountId`
in der XML z.B. `U11114321`, maskiert oder voll — nur die letzten 4 Ziffern zählen):

1. `import_ibkr_trades.py` öffnet die XML, liest `accountId = U11114321` aus dem
   `<FlexStatement>`-Tag.
2. `config.py` extrahiert die letzten 4 Ziffern (`4321`) und schlägt sie in `accounts.toml`
   nach → Treffer: `user = "anna"`, `environment = "money"`.
3. Für den Tabellen-Prefix wird zusätzlich `users.toml` nachgeschlagen: `anna` → `anna_`.
4. Ergebnis: Die Trades aus dieser Datei landen in `ibkr_money.anna_trades_raw` — DB-Zugang
   dafür kommt aus `.env` (Schritt 1 dort war nur "wie verbinde ich mich", nicht "wessen
   Daten sind das").
5. Beim nächsten `run_pipeline.py`-Lauf (ohne `--users`/`--envs`-Filter) prüft `pipeline.toml`:
   ist `anna`/`money` dort eingetragen? Ja → wird im `process`-Step mitverarbeitet.

**Jetzt zieht Annas Bruder Tom mit ein**, eigenes Paper-Konto, dieselbe Maschine:

- `users.toml` bekommt einen neuen Block `[tom]` mit `prefix = "tom_"` (lokal — auf jeder
  Maschine, die Toms Daten verarbeitet, ebenso ergänzen).
- `accounts.toml` bekommt einen neuen Eintrag für Toms accountId-Suffix, z.B.
  `[2468] user = "tom" / environment = "paper"` (nur lokal, nicht geteilt).
- `pipeline.toml` bekommt `[users.tom] environments = ["paper"]` — **aber erst, nachdem**
  `python -m tools.maintenance.reset_IBKR_DB paper tom_` gelaufen ist. Vorher würde
  `run_pipeline.py` beim `process`-Step mit "Tabelle nicht gefunden" abbrechen, weil
  `tom_trades_raw` noch gar nicht existiert.
- `.env` bleibt unverändert — DB-Zugangsdaten sind nicht pro Person, sondern pro Maschine.

**Alle vier Dateien im Endzustand, nachdem Tom eingezogen ist:**

```ini
# .env — unverändert
DB_USER=root
DB_PASS=geheim123
DEFAULT_USER=anna
```

```toml
# users.toml (lokal) — neuer Block [tom]
[anna]
prefix = "anna_"

[tom]
prefix = "tom_"
```

```toml
# accounts.toml — neuer Eintrag [2468]
[4321]
user = "anna"
environment = "money"

[8765]
user = "anna"
environment = "paper"

[2468]
user = "tom"
environment = "paper"
```

```toml
# pipeline.toml — neuer Block [users.tom]
[users.anna]
environments = ["money", "paper"]

[users.tom]
environments = ["paper"]
```

---

## 10. Fehlerbehandlung & Robustheit

### 10.1 Duplikat-Schutz

- **Checksum-basiert:** Verhindert Doppel-Import derselben XML
- **`processed`-Flag:** Verhindert Doppel-Processing desselben Trades
- **`campaign_ledger`-Atomizität:** Kein Ledger-Eintrag ohne dazugehörigen Trade

### 10.2 Logging

Jede Phase schreibt in `log/` mit Timestamp. Logger-Ebenen:
```
DEBUG   → detaillierte FIFO-Schritte
INFO    → Trade-Ergebnisse, Kampagnen-Status
WARNING → fehlende Daten, unerwartete Fälle
ERROR   → Fehler mit Stacktrace (kein Absturz der Pipeline)
```

---

## 11. Ausblick — Erweiterungen & Verbesserungen

### 11.1 Kurzfristige Verbesserungen

#### A) Streaming-Processing statt Batch
```
Problem:   Alle Trades werden in RAM geladen (DataFrame)
Risiko:    Bei sehr großen Historien (10.000+ Trades) hoher Speicherbedarf
Lösung:    Generator-basiertes Streaming — trades_raw zeilenweise verarbeiten
           (yield-Pattern bereits in Teilen vorhanden)
```

#### B) Automatische Retry-Logik
```
Problem:   Bei Datenbankfehler mid-Processing: unklar welche Trades schon verarbeitet
Lösung:    Idempotente Operationen + Retry-Counter in trades_raw
           (max_retries=3 → FAILED-Status nach Erschöpfung)
```

#### C) Validierungs-Report beim Import
```
Aktuell:   Fehler landen im Log, keine strukturierte Auswertung
Verbesserung: 
  - Anzahl importierter / übersprungener / fehlerhafter Trades als JSON
  - Webhook-Notification bei Fehlern (Slack, E-Mail)
```

### 11.2 Mittelfristige Erweiterungen

#### D) Broker-Agnostik: Weitere Datenquellen
```
Problem:   System ist auf IBKR FlexQuery fixiert
Potential: Andere Broker (Tastyworks, TD Ameritrade) über Adapter anbinden

Ansatz: BrokerAdapter-Interface
  ├── IBKRFlexAdapter (bestehend)
  ├── TastyworksAdapter (CSV-Format)
  └── GenericCSVAdapter (konfigurierbar)

Der Parser-Orchestrator (flex_parser.py) ruft nur das Interface auf.
```

#### E) Real-Time-Import via IBKR TWS API
```
Aktuell:   Täglicher Batch-Import via E-Mail
Potential: Live-Import via IBKR TWS API (Interactive Brokers API)
           → Trades werden sekündlich importiert
           → Dashboard zeigt Live-P&L

Anforderungen:
  - ibapi Python-Paket
  - Separater Service-Prozess (always-on)
  - trades_raw als Puffer bleibt bestehen
```

#### F) Erweitertes Strategie-Tracking
```
Aktuell:   Strategie-Name wird beim Import gesetzt und bleibt statisch
Potential:
  - Strategie-Zustand über Laufzeit tracken (z.B. IC: welcher Flügel getroffen?)
  - Automatisches Rollover-Erkennen (gleiche Strategie, neue Expiry)
  - Greeks-Snapshot bei Eröffnung (via TWS API)
```

#### G) Steuer-Export
```
Potential: Automatischer Export als:
  - FIFO-Steuerreport (Österreich/Deutschland)
  - CSV für Steuerberater
  - Vergleich mit IBKR Annual Tax Report

Basis: trades_close enthält alle nötigen Daten
```

#### H) Währungsdarstellung USD/EUR in der Weboberfläche
```
Aktuell:   Weaver führt alle Beträge zusätzlich in EUR mit (*_EUR / *_eur-Spalten in
           trades_close und campaign_ledger, fxRateToBase in trades_raw / trades_open).
           Beide Währungen gleichzeitig zeigen aber nur die Detailseiten geschlossener
           Trades; Listen, Kampagnen, Spreads und Statistiken zeigen die Handelswährung.
Ziel:      Globaler Umschalter USD/EUR (analog zum Environment-Schalter) oder
           EUR-Werte überall mit anzeigen.
Basis:     Daten liegen vollständig vor — reine Erweiterung der Laravel-Oberfläche.
```

### 11.3 Langfristige Architektur-Ideen

#### I) Event-Sourcing statt FIFO-Matching on-the-fly
```
Aktuelles Modell:
  trades_raw → FIFO-Matching → trades_open + trades_close

Event-Sourcing-Ansatz:
  Alle Ereignisse (TradeOpened, TradeClosed, PositionSplit, ...) in
  einer "events"-Tabelle speichern.
  Aktueller Zustand = Replay aller Events.

Vorteil: Zeitreise möglich (wie sah P&L am 15.03. aus?)
         Kampagnen rückwirkend neu berechnen ohne Datenverlust
Nachteil: Komplexer, langsamer Read-Pfad
```

#### J) Plugin-System für Corporate Actions
```
Aktuell:   Splits werden hardcoded behandelt
Potential: Jeder CorporateAction-Typ = eigener Handler (Plugin)
           → einfaches Erweitern ohne Kerncode zu ändern

class CorporateActionHandler(ABC):
    @abstractmethod
    def handle(self, action, repo, tracker): ...

class SplitHandler(CorporateActionHandler): ...
class DividendHandler(CorporateActionHandler): ...
class MergerHandler(CorporateActionHandler): ...
```

#### K) Tagesabschluss-Snapshot
```
Potential: Tägliche Bestandsaufnahme als separater DB-Eintrag:
  - Open P&L je Symbol (unrealisiert)
  - Margin-Verbrauch
  - Greeks-Summe (Delta, Theta, Vega)
  
Basis: Kombination aus trades_open + account_snapshots + TWS API
```

---

## Anhang: Technologie-Stack

| Komponente | Technologie | Version |
|---|---|---|
| Sprache | Python | 3.14 |
| Datenbank | MySQL | 8.4 |
| ORM/DB-Driver | SQLAlchemy + PyMySQL | 2.0.x + 1.1.x |
| Daten-Manipulation | pandas | aktuelle |
| Dezimal-Arithmetik | Python `decimal` | stdlib |
| XML-Parsing | Python `xml.etree.ElementTree` | stdlib |
| Konfiguration | python-dotenv | aktuelle |
| Pipeline-Config | TOML | stdlib (Python 3.11+) |
| Tests | pytest | aktuelle |

---

## Anhang: Wichtige Dateipfade

```
TradingJournal-Weaver/
├── run_pipeline.py              ← Einstiegspunkt (orchestriert alle Phasen)
├── pipeline.toml                ← Pipeline-Konfiguration (aktive User/Environments, Steps) — maschinenspezifisch, gitignored
├── users.toml                   ← Zentrale User↔Prefix-Registry — lokal, gitignored (Vorlage: users.toml.example)
├── README.md                    ← Projekt-Kurzbeschreibung
├── src/
│   ├── get_flexquery_emails.py  ← Phase 0: IMAP-Abruf → incoming_mail/ + Trade_CSV/incoming
│   ├── get_flexquery_api.py     ← Phase 0 zweiter Kanal: FlexQuery via Web-API → incoming_api/
│   ├── import_ibkr_trades.py    ← Phase 1: XML/CSV-Import → trades_raw
│   ├── process_ibkr_trades.py   ← Phase 2: FIFO-Processing → Endtabellen
│   ├── xml_append_summary.py    ← Phase 3: Summary-XML für DB-Rebuild
│   ├── import_activity_statement.py ← CSV-Snapshot-Import (account_snapshots)
│   ├── import_csv_snapshots.py  ← Snapshot-Step der Pipeline (Activity-CSVs, TWRR exakt)
│   ├── config.py                ← get_engine(), get_account_config(), DB_MAP, load_users(), TABLE_PREFIX
│   ├── trade_enums.py           ← TradeStatus, AssetCategory, CampaignStatus
│   ├── options_pnl.py           ← calculate_pnl()/get_position_summary(), von flex_parser.py verwendet (Produktivcode, kein dev-Tool)
│   ├── parsers/
│   │   ├── flex_parser.py       ← XML-Orchestrator (process_flex_file)
│   │   ├── day_trade_processor.py  ← Element-Extraktion (Trades, EAE, CorpActions)
│   │   ├── option_strategies.py ← Strategie-Erkennung (ibOrderID + 3s-Fallback)
│   │   ├── inventory_tracker.py ← Kampagnen-Lifecycle + Running Balance
│   │   └── activity_csv_parser.py ← Activity-Statement-CSV-Parser
│   ├── book_trades.py           ← BookTrade-Klassifizierung via OptionEAE (Top-Level, nicht in parsers/)
│   ├── trade_schemas/
│   │   ├── base_schema.py       ← Abstrakte Basis (validate, REQUIRED_FIELDS)
│   │   ├── open_trade.py        ← OpenTradeSchema + to_closed_trade() + ratio-Skalierung
│   │   └── closed_trade.py      ← ClosedTradeSchema
│   ├── db/
│   │   └── db_access.py         ← DBAccess (SQL) + TradeRepository (Domain-Queries)
│   └── utils/
│       ├── div_utils.py         ← to_decimal(), compute_checksum(), calculate_hold_metrics()
│       ├── corporate_utils.py   ← SPLIT_TYPES (RS, SS, FS)
│       └── path_utils.py        ← get_project_root()
├── tools/
│   └── maintenance/
│       ├── reset_IBKR_DB.py     ← DB-Reset (destruktiv! alle Tabellen inkl. trades_raw)
│       ├── setup_psychology_tables.py ← legt psychology_*-Tabellen an (nicht-destruktiv)
│       ├── seed_psychology_rulesets.py ← Basisdaten für Psychology-Modul
│       ├── fix_symbol_mismatch.py / purge_stale_trades.py ← punktuelle Datenkorrekturen
│       └── xml_summary_creator.py ← Summary-XML manuell erzeugen
├── sql/                         ← DB-Schema-Dateien (__PREFIX__ Platzhalter)
│   ├── trades_raw.sql
│   ├── trades_open.sql
│   ├── trades_close.sql
│   ├── trading_campaigns.sql
│   └── campaign_ledger.sql      ← inkl. cum_pnl, cum_commission, cum_premium
├── docs/
│   └── handbuch/                ← Benutzer- und technisches Handbuch (gespiegelt aus trading/docs/)
│       ├── benutzer/            ← Überblick, IBKR einrichten, Installation für Einsteiger, Alltag, Updates
│       └── technik/             ← u. a. diese Dokumentation (10-…), Befehlsreferenz (30-…), Installation
├── dev/                         ← Einmal-Migrationen, persönliche Tools — nie für einen
│   │                               frischen Rechner nötig, absichtlich nicht in
│   │                               sql/src/tools/maintenance (siehe Sparse-Checkout-Hinweis
│   │                               in 40-installation-windows.md für schlanke Installationen)
│   ├── migrate_running_balance.py ← Migration: cum_pnl/cum_commission/cum_premium
│   ├── migrate_add_campaign_id_to_trade_planner.py
│   ├── migrate_add_fees_open_to_trade_planner.py
│   ├── migrate_add_open_types_to_psychology.py
│   ├── migrate_backfill_assignment_linkid.py
│   ├── compare_tat_ibkr.py      ← manueller TAT-vs-IBKR-Abgleich
│   └── setup.py                 ← veraltet/ungenutzt (echter Weg: requirements.txt)
├── tests/                       ← pytest (DummyLogger, DummyDBAccess)
├── input/                       ← Test-XML/CSV-Dateien
└── log/                         ← Anwendungslogs (RotatingFileHandler)
```
