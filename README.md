# Trading Journal 3.0 — xml_proj

Import- und Processing-Pipeline für **IBKR FlexQuery-Reports** (XML) und
**Activity Statements** (CSV). Die Rohdaten werden in ein strukturiertes
Trading-Journal (MySQL) überführt:

- FIFO-Lot-Matching für Aktien, Optionen und FX
- Kampagnen-Tracking je Symbol (ACTIVE → PENDING → CLOSED)
- Options-Strategie-Erkennung (Spreads, Iron Condors, Straddles, …)
- Vollständiger Audit-Trail im `campaign_ledger` (inkl. Running Balance)
- Multi-User (Tabellen-Prefix) und Multi-Environment (money / paper / test / autom_*)

## Ablauf (Kurzfassung)

```
get_flexquery_emails.py   IBKR-Mails abrufen → C:\Trade_XML\incoming\ + C:\Trade_CSV\incoming\
import_ibkr_trades.py     flex.*.xml → trades_raw (Routing per accountId → User/Environment)
process_ibkr_trades.py    FIFO-Matching → trades_open / trades_close / trading_campaigns / campaign_ledger
xml_append_summary.py     Summary-XML je User/Environment (für DB-Rebuild)
```

Alles zusammen über den Pipeline-Runner:

```bash
python run_pipeline.py            # Konfiguration: pipeline.toml
```

## Dokumentation

| Datei | Inhalt |
|---|---|
| `HELP.md` | Befehlsreferenz aller Scripts (Argumente, Beispiele, typische Abläufe) |
| `docs/pipeline-workflow.md` | Technische Gesamtdokumentation (Architektur, FIFO-Logik, DB-Schema) |
| `CLAUDE.md` | Entwickler-Notizen (Module, Konventionen, bekannte Fixes) |
