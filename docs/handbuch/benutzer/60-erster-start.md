# Erster Start — UI-Erstkonfiguration

Was nach der technischen Installation (siehe [Technisches Handbuch: Installation: TradingJournal](../technik/60-installation-tradingjournal.md)
bzw. [TradingJournal installieren](50-tradingjournal-installieren.md)) einmalig einzustellen ist, bevor die App produktiv genutzt wird — und was die einzelnen Bedienelemente in der Oberfläche eigentlich bedeuten.

---

## 1. Einloggen

Mit den Zugangsdaten einloggen, die beim Setup per `php artisan auth:create-user` angelegt wurden („Technisches Handbuch: Installation: TradingJournal“ Schritt 5 bzw. „TradingJournal installieren“  Schritt 4). Es gibt bewusst **keine Registrierungsseite** — ein neuer Zugang entsteht immer nur über diesen einen Befehl auf der Kommandozeile, nie über die Weboberfläche selbst. Das ist Absicht: Es soll niemand "einfach so" ein Konto anlegen können.

## 2. Der Environment-Switcher (oben in der Navigation)

**Was ist ein "Environment"?** 

Ein Environment ist ein abgetrennter Datenbereich — z.B. `MONEY` für echtes Geld, `PAPER` für simuliertes Übungs-Trading, `TEST` zum Ausprobieren. Jedes Environment hat seine eigenen, komplett getrennten Daten; ein Trade im TEST-Bereich taucht niemals im MONEY-Bereich auf und umgekehrt. Der Dropdown oben in der Navigation schaltet zwischen diesen Bereichen um.

**Warum sieht man dort nicht automatisch alle Environments?** 

Der Dropdown zeigt nur die Environments an, für die beim eigenen Nutzer-Konto auch wirklich schon Datenbank-Tabellen angelegt wurden (Schritt "Datenbank-Tabellen anlegen" beim `xml_proj`-Setup). Fehlt ein Environment im Dropdown, ist das **kein Fehler** — es bedeutet nur, dass für dieses Environment noch keine Tabellen existieren. Sobald das nachgeholt wird (`reset_IBKR_DB.py <env> <prefix>` in `xml_proj`), erscheint es automatisch. **TEST** ist immer sichtbar, auch ganz ohne Tabellen — als sicherer Ausgangspunkt.

⚠️ **Falle, die für Verwirrung sorgen kann:** 

Nach dem nachträglichen Anlegen eines Environments kann es bis zu **10 Minuten** dauern, bis es im Dropdown erscheint (die App merkt sich das Ergebnis kurzzeitig, um nicht bei jedem Klick erneut in der Datenbank nachzusehen). Wer es sofort sehen will, statt zu warten: auf der Kommandozeile im `TradingJournal`-Ordner `php artisan cache:clear` ausführen.

Direkt nach dem allerersten Login (bevor irgendetwas ausgewählt wurde) steht der Schalter automatisch auf **TEST**.

## 3. Mehrere Personen nutzen dasselbe TradingJournal ("Nutzer wechseln")

Dieser Punkt ist nur relevant, wenn **mehr als eine Person** dieselbe Installation nutzt
(z.B. zwei Familienmitglieder mit je eigenem IBKR-Konto). Bei nur einer Person kann dieser Abschnitt übersprungen werden.

Wurde beim Anlegen eines Kontos per `auth:create-user` die Option `--admin` gesetzt, sieht dieser Account auf dem Dashboard einen zusätzlichen Dropdown, mit dem er in die Ansicht eines *anderen* angelegten Kontos wechseln kann, **ohne sich neu einzuloggen**. Praktisch, wenn z.B. ein Admin-Konto (Elternteil) kurz nachsehen möchte, wie es beim anderen Konto aussieht — sieht dann exakt das, was die andere Person auch sehen würde, inklusive deren Environment-Auswahl.

Für einen Zwei-Personen-Haushalt reicht es, wenn **eine** der beiden Personen `--admin`
bekommt — die zweite Person braucht das nicht, loggt sich einfach ganz normal mit ihrem eigenen Zugang ein.

## 4. Dashboard-Kacheln anpassen

Über das Zahnrad-Symbol auf dem Dashboard lässt sich auswählen, welche Info-Kacheln (z.B. Profit Factor, größter Gewinn/Verlust, ...) angezeigt werden. Praktisch, um das Dashboard auf das zu reduzieren, was einen wirklich interessiert.
