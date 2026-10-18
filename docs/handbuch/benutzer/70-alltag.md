# Alltag mit dem TradingJournal

Beschreibt den betrieblichen Ablauf aus Nutzersicht: was täglich automatisch passiert, wie
Kampagnen im UI "leben", und welche manuellen Workflows (Trade Log, Psychology) es
zusätzlich zur reinen Datenanzeige gibt. Für die technische Pipeline-Architektur siehe
[`docs/handbuch/technik/10-architektur-und-pipeline.md`](../technik/10-architektur-und-pipeline.md).

---

## 1. Täglicher Datenimport (automatisiert)

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
| `summary`      | Verarbeitete Mail-XMLs in `summary_<prefix><env>.xml` zusammenfassen (Basis für spätere `--from-summary`-Rebuilds)                                                             |

`pipeline.toml` definiert, **welche** User × Environments verarbeitet werden — die Datei
ist maschinenspezifisch (wie `.env`, nicht versioniert, siehe `pipeline.toml.example`):
jede Maschine trägt nur die User/Environments ein, die dort tatsächlich per
`reset_IBKR_DB.py` initialisiert wurden. Beispiel mit zwei Nutzern:

| User | Environments                           |
| ---- | --------------------------------------- |
| anna | money, paper, autom_money, autom_paper  |
| tom  | money                                   |

Für den automatisierten Lauf (z. B. täglich per Windows Task Scheduler oder Cronjob) siehe
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
| Kompletter Neuaufbau eines Environment/Prefix                                           | `reset_IBKR_DB.py` (⚠️ destruktiv) + Re-Import über `--from-summary`                                                                                   |

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
