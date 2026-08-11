# Security Policy

## Unterstützte Version

Es gibt keine Versions-Branches — nur der aktuelle Stand von `master` wird gepflegt.

## Eine Sicherheitslücke melden

**Bitte keine öffentlichen Issues für Sicherheitslücken.** Stattdessen über GitHub Security
Advisories melden: Reiter **Security** → **Report a vulnerability** in diesem Repository.
Das erstellt eine private Meldung, die nur Maintainer und die von dir eingeladenen Personen
sehen.

Da dies ein Hobbyprojekt ohne festes Team ist, gilt best effort statt fester SLA — Meldungen
werden aber priorisiert vor normalen Feature-Issues behandelt.

## Was als Sicherheitslücke zählt

- Wege, an fremde Trading-/Kontodaten anderer User (Multi-User/Multi-Environment via
  Tabellen-Prefix) zu gelangen
- SQL-Injection oder unsichere Deserialisierung beim Verarbeiten von IBKR-XML/-CSV-Importen
- Schwachstellen im FlexQuery-API-Zugriff (`get_flexquery_api.py`), z.B. Token-/Credential-Leaks
- Offenlegung von Secrets aus `.env`/`pipeline.toml` durch das Anwendungsverhalten selbst

**Kein Sicherheitsproblem im Sinne dieser Policy:** Themen, die ausschließlich die eigene
lokale `.env`-Datei oder Maschine betreffen (dafür siehe `docs/git-security.md` im Root-Repo,
sofern verfügbar), oder Fragen zur Zuverlässigkeit von IBKR selbst.
