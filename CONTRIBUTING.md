# Contributing

Danke fürs Interesse an xml_proj. Das Projekt ist ein Hobbyprojekt — Reviews und Antworten
auf Issues/PRs laufen best effort, ohne feste Zeitzusage.

## Bevor du einen PR aufmachst

- Bei größeren Änderungen (neue Pipeline-Schritte, Umbau der FIFO-/Kampagnen-Logik) vorher ein
  Issue aufmachen und den Ansatz skizzieren — die Matching- und Campaign-Logik hat einige
  nicht offensichtliche Regeln (siehe `CLAUDE.md`), die leicht kaputtgehen.
- Kleine, fokussierte PRs statt große Sammel-PRs. Ein PR = eine Änderung.

## Setup

Siehe [`README.md`](README.md) sowie `pip install -e ../shared_python`.

## Tests

```bash
pytest
```

Neue Bugfixes bitte mit Regressionstest einreichen (Fix + Test, der ohne den Fix fehlschlägt,
per Tripwire verifiziert: Fix kurz zurückdrehen → Test muss fehlschlagen).

## Konventionen

- Code-Kommentare und Log-Meldungen: Deutsch
- Variablen- und Funktionsnamen: Englisch
- Finanzwerte immer als `Decimal`, nie als `float` — `to_decimal()` aus `trading_common`
  bzw. `src/utils/div_utils.py` verwenden
- Secrets ausschließlich über `.env` (`os.getenv()`), niemals im Code
- Weitere Architektur-/Modul-Details in [`CLAUDE.md`](CLAUDE.md) und `docs/pipeline-workflow.md`

## Secrets

`.env`/`pipeline.toml` niemals committen. Falls versehentlich doch: sofort im Issue oder per
[SECURITY.md](SECURITY.md) melden statt einen "stillen" Fix-PR aufzumachen — die History muss
bereinigt werden, nicht nur der aktuelle Stand.
