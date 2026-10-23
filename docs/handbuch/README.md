# Handbücher

Die Dokumentation von TradingJournal und TradingJournal-Weaver ist in zwei Handbücher gegliedert,
dazu kommt eine kurze Vorstellung. Jede Datei ist ein Kapitel; die Nummer im Dateinamen gibt die
Reihenfolge vor. Alle drei gibt es auch als gesetztes PDF zum Herunterladen:
[Vorstellung](https://github.com/mike-1140/TradingJournal/releases/latest/download/TradingJournal-Vorstellung.pdf), [Benutzerhandbuch](https://github.com/mike-1140/TradingJournal/releases/latest/download/TradingJournal-Benutzerhandbuch.pdf) und [Technisches Handbuch](https://github.com/mike-1140/TradingJournal/releases/latest/download/TradingJournal-Technisches-Handbuch.pdf) (jeweils die neueste Version; ältere unter [Releases](https://github.com/mike-1140/TradingJournal/releases)).

## Vorstellung

Der schnelle Überblick: warum es das TradingJournal gibt, was es kann und was nicht.

| Kapitel | Inhalt |
|---|---|
| [Vorstellung](vorstellung/10-vorstellung.md) | Motivation, Eckpunkte, Workflow, Pro & Contra, Entstehung |

## Benutzerhandbuch

Für Anwender — von der Einrichtung bei IBKR bis zur täglichen Nutzung, auch ohne
Programmierkenntnisse.

| Kapitel | Inhalt |
|---|---|
| [10 · Überblick](benutzer/10-ueberblick.md) | Vom Trade bis zur Auswertung: wie die Daten fließen |
| [15 · Rundgang durch die App](benutzer/15-rundgang.md) | Alle Bereiche der App mit Screenshots: was wo zu finden ist |
| [20 · IBKR einrichten](benutzer/20-ibkr-einrichten.md) | Flex Queries, E-Mail-Zustellung, Prüfcode, Kontoauszug — mit Screenshots |
| [30 · Windows vorbereiten](benutzer/30-windows-vorbereiten.md) | Benötigte Programme installieren |
| [40 · TradingJournal-Weaver installieren](benutzer/40-weaver-installieren.md) | Datenimport einrichten |
| [50 · TradingJournal installieren](benutzer/50-tradingjournal-installieren.md) | Weboberfläche einrichten |
| [60 · Erster Start](benutzer/60-erster-start.md) | Anmelden (PC vs. Server), Environments, mehrere Benutzer, Dashboard anpassen |
| [70 · Alltag mit dem TradingJournal](benutzer/70-alltag.md) | Daten holen und verarbeiten, Durchgang nach dem Import, Kampagnen, wenn etwas nicht stimmt |
| [75 · Eigener Server](benutzer/75-eigener-server.md) | Was auf einem Server anders ist, wie die Daten hinkommen, automatischer Lauf per Aufgabenplanung |
| [80 · Updates einspielen](benutzer/80-updates.md) | Neue Versionen einspielen |
| [90 · Fehlerbehebung und häufige Fragen](benutzer/90-fehlerbehebung.md) | Häufige Probleme bei Installation, Abruf, Import und Anzeige — mit Lösung |

## Technisches Handbuch

Für technisch Interessierte, den Betrieb auf eigenen Servern und Mitwirkende.

| Kapitel | Inhalt |
|---|---|
| [10 · Architektur und Import-Pipeline](technik/10-architektur-und-pipeline.md) | Import, FIFO-Logik, Kampagnen, Datenbankschema, Konfiguration |
| [20 · Aufbau einer Flex Query](technik/20-aufbau-flexquery.md) | XML-Beispiel und welche Felder der Import liest |
| [30 · Befehlsreferenz](technik/30-befehlsreferenz.md) | Alle Skripte mit Argumenten und Beispielen |
| [40 · Installation: Windows-Grundausstattung](technik/40-installation-windows.md) | Grundausstattung, kompakt |
| [50 · Installation: TradingJournal-Weaver](technik/50-installation-weaver.md) | Setup der Pipeline, kompakt |
| [60 · Installation: TradingJournal](technik/60-installation-tradingjournal.md) | Setup der Weboberfläche, inkl. Apache-VirtualHost |
| [70 · Server-Betrieb](technik/70-server-betrieb.md) | Eigener Server statt lokalem PC, Zugriff per VPN |
| [80 · Verteilter Abruf](technik/80-verteilter-abruf.md) | Minimaler Client nur für den Datenabruf |
| [90 · Bekannte Grenzen und offene Fragen](technik/90-bekannte-grenzen.md) | Was (noch) nicht geht, was ungetestet ist — und wie man mit Beispielen hilft |
