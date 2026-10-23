# Eigener Server

Statt auf dem eigenen PC können TradingJournal-Weaver und TradingJournal auch auf einem eigenen
Server laufen — einem gemieteten Windows-Server oder einem Rechner, der dauerhaft eingeschaltet
bleibt. Das lohnt sich, wenn du von mehreren Geräten (PC, Notebook, unterwegs) auf **dasselbe**
Journal zugreifen möchtest, oder wenn der eigene PC nicht jeden Tag läuft.

> [!TIP]
> TradingJournal braucht wenig Leistung. Auf einem Windows-Server von Strato, wie ihn PJM für
> den automatisierten Handel vorschlägt, läuft es problemlos neben dem übrigen Betrieb — wer
> einen solchen Server ohnehin hat, braucht keinen zusätzlichen.

Die ausführliche technische Anleitung steht im technischen Handbuch unter [Server-Betrieb —
TradingJournal auf einem eigenen Server](../technik/70-server-betrieb.md). Dieses Kapitel
erklärt, was dabei gleich bleibt und was anders ist.

## 1. Was gleich bleibt

Die Installation ist im Grunde dieselbe wie auf dem eigenen PC — nur dass du sie per
Fernzugriff (Remote Desktop/RDP oder ein ähnliches Programm) direkt auf dem Server ausführst:
dieselben Programme ([Windows vorbereiten](30-windows-vorbereiten.md)), dieselbe Einrichtung
([TradingJournal-Weaver installieren](40-weaver-installieren.md),
[TradingJournal installieren](50-tradingjournal-installieren.md)), dieselben Einstellungsdateien. Auch der Alltag ist derselbe: ein Lauf von `run_pipeline.py`
holt und verarbeitet die Daten ([Alltag mit dem TradingJournal](70-alltag.md)).

## 2. Was anders ist

| | Eigener PC | Server |
|---|---|---|
| **Erreichbar** | nur auf diesem PC | von allen eigenen Geräten — aber **nur über ein VPN** (z. B. Tailscale), nie offen im Internet |
| **Webserver** | `php artisan serve` im offenen Fenster, oder Apache | Apache, startet mit Windows und läuft dauerhaft |
| **Anmelden** | kein Login, der Admin ist automatisch angemeldet | Login-Seite, jede Person mit eigenem Zugang (`APP_ENV=production` in der `.env` von TradingJournal) |
| **Andere Benutzer ansehen** | über den Benutzer-Dropdown | nicht möglich, jede Person sieht nur ihre Daten |
| **Start-Environment** | TEST | am besten `TRADING_DEFAULT_ENV=MONEY` in der `.env` von TradingJournal |
| **Datenlauf** | von Hand oder per Aufgabenplanung | per Aufgabenplanung (Abschnitt 4) oder angestoßen von einem anderen Rechner (Abschnitt 3) |

> [!WARNING]
> TradingJournal hat keinen eigenen Schutz gegen das massenhafte Durchprobieren von Passwörtern
> und ist nicht dafür gebaut, offen im Internet zu stehen. Der Server muss deshalb **nur über ein
> VPN** erreichbar sein — wie das geht, zeigt die technische Anleitung.

Wie Anmelden und Benutzer auf PC und Server im Detail funktionieren, beschreibt [Erster Start —
UI-Erstkonfiguration](60-erster-start.md).

## 3. Wie die Daten auf den Server kommen

Es gibt zwei Wege. Wichtig ist, dass für einen Tag immer **nur ein** Rechner die Daten abholt:
Der Mail-Abruf löscht die abgeholten Mails, und die Web-API soll ohnehin höchstens einmal am Tag
gefragt werden.

**Weg A — der Server holt selbst.** Mail-Abruf und Web-API laufen direkt auf dem Server, als
Teil des normalen Laufs. Das ist der einfachste Weg; der Lauf startet automatisch per
Aufgabenplanung (Abschnitt 4).

> [!CAUTION]
> Bei Weg A liegen die **Zugangsdaten** auf dem Server: das Passwort des Postfachs und die
> IBKR-Prüfcodes für die Web-API stehen dort in der `.env` von TradingJournal-Weaver. Wer das
> nicht möchte — etwa weil der Server bei einem Anbieter steht —, nimmt Weg B: Dann bleiben die
> Zugangsdaten auf dem eigenen Rechner, und auf dem Server liegen nur die abgeholten Berichte.
> Aus diesem Grund war ursprünglich nur Weg B vorgesehen.

**Weg B — ein anderer Rechner holt ab und überträgt.** Mail-Abruf und Web-API laufen auf einem
anderen Rechner, etwa dem eigenen PC oder einem Reise-Notebook. Ein kleines Skript
(`push-to-server.ps1`) überträgt die abgeholten Dateien — Flex Queries (XML) und Kontoauszüge
(CSV) — per SSH auf den Server und startet dort den Lauf, der sie verarbeitet. Erfolgreich
übertragene Dateien verschiebt es auf dem abholenden Rechner in einen Ablageordner
(`C:\Trade_XML\pushed\…`, `C:\Trade_CSV\pushed`), damit sie beim nächsten Mal nicht erneut
übertragen werden. Auf diesem Rechner braucht es nur eine Minimal-Installation — ohne Datenbank
und ohne Weboberfläche. Die Anleitung steht im technischen Handbuch unter [Verteilter Abruf —
minimaler Client für den Datenabruf](../technik/80-verteilter-abruf.md).

## 4. Automatisch laufen lassen (Windows-Aufgabenplanung)

Damit der Lauf jeden Tag von selbst startet — auf dem Server, aber genauso auf dem eigenen PC —,
legst du einmal eine Aufgabe in der Windows-Aufgabenplanung an:

1. **[Windows]** Windows-Taste drücken, `Aufgabenplanung` eintippen, öffnen.
2. Rechts **Einfache Aufgabe erstellen…** — Name z. B. `TradingJournal Pipeline`.
3. Trigger **Täglich**, Uhrzeit z. B. **18:00**. Die Mails zu einem Handelstag kommen am
   folgenden Nachmittag ([IBKR einrichten — Flex Queries und Kontoauszug](20-ibkr-einrichten.md),
   Abschnitt 4); ein Lauf am frühen Abend erwischt sie zuverlässig.
4. Aktion **Programm starten**, dann eintragen (Pfade an die eigene Installation anpassen):

   | Feld | Inhalt |
   |---|---|
   | Programm/Skript | `C:\Users\<dein Anmeldename>\trading\TradingJournal-Weaver\.venv\Scripts\python.exe` |
   | Argumente hinzufügen | `run_pipeline.py` |
   | Starten in | `C:\Users\<dein Anmeldename>\trading\TradingJournal-Weaver` |

5. Vor **Fertig stellen** den Haken bei **Beim Klicken auf „Fertig stellen“ die Eigenschaften
   für diese Aufgabe öffnen** setzen. In den Eigenschaften auf der Registerkarte **Allgemein**
   **Unabhängig von der Benutzeranmeldung ausführen** wählen und mit **OK** bestätigen (fragt nach
   dem Windows-Passwort).

Ob es geklappt hat: In der Aufgabenplanung zeigt die Spalte *Letztes Ausführungsergebnis* nach
dem ersten Lauf `(0x0)`; in der App sind die neuen Daten da. Zum Ausprobieren lässt sich die
Aufgabe per Rechtsklick → **Ausführen** sofort starten.

## 5. Updates

Ein Update läuft auf dem Server genauso wie auf dem PC: per Fernzugriff verbinden und im Ordner
`TradingJournal` `.\update.ps1` starten ([Updates einspielen](80-updates.md)). Holt bei Weg B ein
anderer Rechner die Daten ab, dort im Ordner `TradingJournal-Weaver` zusätzlich `git pull`
ausführen, damit auch der Abruf auf dem neuesten Stand ist.
