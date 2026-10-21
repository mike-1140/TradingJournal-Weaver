# Erster Start — UI-Erstkonfiguration

Was nach der technischen Installation (siehe [Technisches Handbuch: Installation: TradingJournal](../technik/60-installation-tradingjournal.md)
bzw. [TradingJournal installieren](50-tradingjournal-installieren.md)) einmalig einzustellen ist, bevor die App produktiv genutzt wird — und was die einzelnen Bedienelemente in der Oberfläche eigentlich bedeuten.

TradingJournal verhält sich unterschiedlich, je nachdem, wo es läuft. Maßgeblich ist die
Einstellung `APP_ENV` in der `.env` von TradingJournal:

| | **Auf dem eigenen PC** (`APP_ENV=local`, so wie bei der Installation in „TradingJournal installieren“) | **Auf einem Server** (`APP_ENV=production`, siehe Technisches Handbuch „Server-Betrieb“) |
|---|---|---|
| Anmelden | **kein Login** — die App meldet automatisch den zuerst angelegten Benutzer an | Login-Seite, jede Person mit eigenem Zugang |
| Andere Benutzer ansehen | als Admin über den Benutzer-Dropdown (Abschnitt 3) | nicht möglich |

---

## 1. Anmelden

Benutzer werden beim Setup per `php artisan auth:create-user` angelegt („Technisches Handbuch: Installation: TradingJournal“ Schritt 5 bzw. „TradingJournal installieren“ Schritt 4). Es gibt bewusst **keine Registrierungsseite** — ein neuer Zugang entsteht immer nur über diesen einen Befehl auf der Kommandozeile, nie über die Weboberfläche selbst. Das ist Absicht: Es soll niemand "einfach so" ein Konto anlegen können.

**Auf dem eigenen PC** erscheint keine Login-Seite: Beim Öffnen der App wird automatisch der
**zuerst angelegte Benutzer** angemeldet (der mit der internen Nummer 1). Deshalb sollte das der
eigene Admin-Zugang sein — so wie in der Installationsanleitung mit `--admin` angelegt.

**Auf einem Server** meldet sich jede Person mit E-Mail-Adresse und Passwort an, die beim
Anlegen vergeben wurden.

## 2. Der Environment-Switcher (oben in der Navigation)

**Was ist ein "Environment"?** 

Ein Environment ist ein abgetrennter Datenbereich — z.B. `MONEY` für echtes Geld, `PAPER` für simuliertes Übungs-Trading, `TEST` zum Ausprobieren. Jedes Environment hat seine eigenen, komplett getrennten Daten; ein Trade im TEST-Bereich taucht niemals im MONEY-Bereich auf und umgekehrt. Der Dropdown oben in der Navigation schaltet zwischen diesen Bereichen um.

**Warum sieht man dort nicht automatisch alle Environments?** 

Der Dropdown zeigt nur die Environments an, für die beim eigenen Nutzer-Konto auch wirklich schon Datenbank-Tabellen angelegt wurden (Schritt "Datenbank-Tabellen anlegen" beim `TradingJournal-Weaver`-Setup). Fehlt ein Environment im Dropdown, ist das **kein Fehler** — es bedeutet nur, dass für dieses Environment noch keine Tabellen existieren. Sobald das nachgeholt wird (`reset_IBKR_DB.py <env> <prefix>` in `TradingJournal-Weaver`), erscheint es automatisch.

**TEST** steht immer im Dropdown — als sicherer Ausgangspunkt zum Ausprobieren. Damit es auch funktioniert, braucht es wie jedes Environment Tabellen; die Installationsanleitung legt sie deshalb immer mit an ([TradingJournal-Weaver installieren](40-weaver-installieren.md), Schritt 4). Fehlen sie doch, zeigt die App beim Auswählen von TEST eine Fehlermeldung.

⚠️ **Falle, die für Verwirrung sorgen kann:** 

Nach dem nachträglichen Anlegen eines Environments kann es bis zu **10 Minuten** dauern, bis es im Dropdown erscheint (die App merkt sich das Ergebnis kurzzeitig, um nicht bei jedem Klick erneut in der Datenbank nachzusehen). Wer es sofort sehen will, statt zu warten: auf der Kommandozeile im `TradingJournal`-Ordner `php artisan cache:clear` ausführen.

**Startwert:** Beim Öffnen der App (auf dem Server: nach jedem Login) steht der Schalter zunächst
auf **TEST**. Wer lieber direkt in einem anderen Bereich landen möchte, trägt in der `.env` von
TradingJournal z. B. `TRADING_DEFAULT_ENV=MONEY` ein. Hat der Benutzer im Startwert keine
Tabellen, startet die App stattdessen im ersten Environment, für das es welche gibt (Reihenfolge
MONEY, PAPER, TEST, AUTOM_MONEY, AUTOM_PAPER).

## 3. Mehrere Personen nutzen dasselbe TradingJournal

Dieser Punkt ist nur relevant, wenn **mehr als eine Person** dieselbe Installation nutzt
(z.B. zwei Familienmitglieder mit je eigenem IBKR-Konto). Bei nur einer Person kann dieser Abschnitt übersprungen werden.

**Auf einem Server** ist das einfach: Jede Person hat ihren eigenen Zugang, meldet sich damit an
und sieht nur ihre eigenen Daten. Einen Wechsel zwischen Benutzern gibt es dort nicht.

**Auf dem eigenen PC** gibt es keine Anmeldung (Abschnitt 1) — wie kommt die zweite Person an
ihre Daten? Über den **Benutzer-Dropdown** auf dem Dashboard, rechts neben dem Zahnrad. Er
erscheint nur beim Admin-Zugang (angelegt mit `--admin`):

1. Beim Öffnen der App ist automatisch der Admin angemeldet, der Environment-Schalter steht auf
   TEST. Der Admin sieht seine eigenen Environments; im Benutzer-Dropdown stehen zusätzlich die
   anderen Benutzer zur Auswahl.
2. Ein Klick auf einen anderen Benutzer wechselt zu dessen Daten: Der Environment-Schalter zeigt
   jetzt **dessen** Environments, Dashboard und alle Listen zeigen dessen Trades. Ein Passwort
   braucht es dafür nicht.
3. Als dieser Benutzer gibt es keinen Benutzer-Dropdown mehr — weitere Benutzer lassen sich von
   hier aus nicht auswählen.
4. **Zurück zum Admin:** rechts oben auf **Abmelden** klicken (Symbol Pfeil aus Kasten, neben
   dem Benutzernamen). Auf dem eigenen PC führt das nicht zu einer Login-Seite — die App meldet
   sofort wieder automatisch den Admin an.

Wer gerade angemeldet ist, steht immer rechts oben neben dem Abmelden-Knopf.

Für einen Zwei-Personen-Haushalt reicht es also, wenn **eine** Person `--admin` bekommt — die
zweite Person braucht das nicht. Ihr Zugang wird trotzdem mit `auth:create-user` angelegt (mit
eigenem Präfix), damit es ihre Daten überhaupt gibt.

## 4. Dashboard-Kacheln anpassen

Über das Zahnrad-Symbol auf dem Dashboard lässt sich auswählen, welche Info-Kacheln (z.B. Profit Factor, größter Gewinn/Verlust, ...) angezeigt werden. Praktisch, um das Dashboard auf das zu reduzieren, was einen wirklich interessiert.

Die Auswahl wird **je Environment** und je Benutzer gespeichert — im Fenster steht „Kacheln für MONEY“, „Kacheln für PAPER“ usw. So kann z. B. das Paper-Dashboard schlanker sein als das Echtgeld-Dashboard. Solange nichts ausgewählt wurde, sind alle Kacheln eingeschaltet. Kontostands-Kacheln (NAV, Cash, TWRR) erscheinen nur, wenn für das Environment ein Kontoauszug eingelesen wurde (siehe [IBKR einrichten — Flex Queries und Kontoauszug](20-ibkr-einrichten.md), Abschnitt 6).
