# Contributing

Danke fürs Interesse an TradingJournal-Weaver. Das Projekt ist ein Hobbyprojekt — Reviews und Antworten
auf Issues/PRs laufen best effort, ohne feste Zeitzusage.

## Bevor du einen PR aufmachst

- Bei größeren Änderungen (neue Pipeline-Schritte, Umbau der FIFO-/Kampagnen-Logik) vorher ein
  Issue aufmachen und den Ansatz skizzieren — die Matching- und Campaign-Logik hat einige
  nicht offensichtliche Regeln (siehe `CLAUDE.md`), die leicht kaputtgehen.
- Kleine, fokussierte PRs statt große Sammel-PRs. Ein PR = eine Änderung.

## Setup

Siehe [`README.md`](README.md).

## Tests

```bash
pytest
```

Neue Bugfixes bitte mit Regressionstest einreichen (Fix + Test, der ohne den Fix fehlschlägt,
per Tripwire verifiziert: Fix kurz zurückdrehen → Test muss fehlschlagen).

## Konventionen

- Code-Kommentare und Log-Meldungen: Deutsch
- Variablen- und Funktionsnamen: Englisch
- Finanzwerte immer als `Decimal`, nie als `float` — `to_decimal()` aus `src/utils/div_utils.py`
  bzw. `src/utils/div_utils.py` verwenden
- Secrets ausschließlich über `.env` (`os.getenv()`), niemals im Code
- Weitere Architektur-/Modul-Details in [`CLAUDE.md`](CLAUDE.md) und `docs/handbuch/technik/10-architektur-und-pipeline.md`

## Beispieldaten beisteuern

Auch ohne Code hilfst du viel, wenn in deinem Konto ein Fall aus
[Beispiele gesucht](BEISPIELE-GESUCHT.md) vorgekommen ist — ein Pull Request ist dafür nicht nötig:

1. Den Fall in [Beispiele gesucht](BEISPIELE-GESUCHT.md) suchen (Nummer merken).
2. Die Flex-Query-XML des Tages holen und **anonymisieren** — Kontonummer überall ersetzen,
   Trade-IDs, Kurse und Mengen lassen. Anleitung: `docs/handbuch/technik/90-bekannte-grenzen.md`,
   Abschnitt „Mithelfen“.
3. Melden: am besten im Forum, in dem das TradingJournal vorgestellt wurde, oder mit GitHub-Konto
   als Issue im Repository `TradingJournal-Weaver` mit der Vorlage
   [„Beispiel für ungetesteten Fall“](https://github.com/mike-1140/TradingJournal-Weaver/issues/new?template=beispiel.yml).

## Secrets

`.env`/`pipeline.toml`/`accounts.toml` niemals committen. Falls versehentlich doch: sofort im Issue oder per
[SECURITY.md](SECURITY.md) melden statt einen "stillen" Fix-PR aufzumachen — die History muss
bereinigt werden, nicht nur der aktuelle Stand.

## Lizenz deiner Beiträge

Das Projekt steht unter der [PolyForm Noncommercial License 1.0.0](LICENSE). Mit dem Einreichen
eines Pull Requests bestätigst du, dass du die Rechte an deinem Beitrag besitzt, und räumst dem
Projektinhaber (mike-1140) ein unbefristetes, unentgeltliches und nicht-exklusives Recht ein,
den Beitrag unter der Projektlizenz **und** unter künftigen oder zusätzlichen Lizenzen
(einschließlich separater kommerzieller Lizenzen) zu nutzen, zu ändern und weiterzugeben. Deine
eigenen Rechte an deinem Beitrag bleiben davon unberührt.
