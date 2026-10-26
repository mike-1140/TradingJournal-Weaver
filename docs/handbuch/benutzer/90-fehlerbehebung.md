# Fehlerbehebung und häufige Fragen

Dieses Kapitel sammelt Probleme, die bei Einrichtung und Betrieb auftreten können, mit Ursache
und Lösung. Es wächst mit den Fragen aus der Praxis — wer auf ein Problem stößt, das hier fehlt,
meldet es gerne: **für den Anfang im Forum**, in dem das TradingJournal vorgestellt wurde.
Fragen, die öfter kommen, werden dort gesammelt und zu einer FAQ zusammengefasst; erst in einem
späteren Schritt laufen Meldungen über GitHub (siehe [Vorstellung](../vorstellung/10-vorstellung.md),
Abschnitt „Status“).

> [!WARNING]
> Bei Fragen in Foren oder auf GitHub **niemals** echte Kontonummern, Flex-Query-Dateien,
> Prüfcodes (Token) oder unmaskierte Screenshots weitergeben. Für die Fehlersuche reicht fast
> immer die Fehlermeldung aus dem Protokoll.

## 1. Zuerst nachsehen: die Protokolle

Die meisten Probleme lassen sich an einer Meldung in den Protokolldateien erkennen:

| Programm                | Protokolldatei                                 |
| ----------------------- | ---------------------------------------------- |
| TradingJournal-Weaver   | `TradingJournal-Weaver\log\app.log`             |
| TradingJournal (Weboberfläche) | `TradingJournal\storage\logs\laravel.log`      |

Dazu kommt im Journal selbst die Seite **Raw Data** (unter *Analyse*): Steht ein Trade dort,
ist er angekommen und das Problem liegt in Verarbeitung oder Anzeige. Fehlt er, liegt es vor
dem Import — beim Bericht, bei der Mail oder bei der Kontozuordnung.

## 2. Installation

**„Fatal error in launcher: Unable to create process using …“**

Tritt auf, nachdem der Projektordner verschoben oder umbenannt wurde. Die virtuelle
Python-Umgebung (`.venv`) enthält feste Pfade und funktioniert am neuen Ort nicht mehr. Lösung:
die Umgebung neu anlegen.

PowerShell, im Ordner `TradingJournal-Weaver`:

```powershell
Remove-Item -Recurse -Force .venv
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**„Vite manifest not found at: …\public\build\manifest.json“**

Die Weboberfläche zeigt diese Fehlerseite, wenn Farben, Icons und Layout noch nicht gebaut
wurden. Lösung: im Ordner `TradingJournal` einmal `npm run build` ausführen (Kapitel
[TradingJournal installieren](50-tradingjournal-installieren.md), Schritt „Optik der Seite
bauen“). Beim Einspielen von Updates mit `update.ps1` geschieht das automatisch.

**„UnicodeDecodeError: 'utf-8' codec can't decode byte 0xef …“ (oder `0xff`) beim Start**

Eine Konfigurationsdatei wie `pipeline.toml` oder `accounts.toml` wurde mit einer
unpassenden Kodierung gespeichert — typischerweise, wenn sie per PowerShell
(`Set-Content`, `>`) erzeugt wurde. Lösung: die Datei im Text-Editor öffnen und mit der Kodierung
**UTF-8** (nicht „UTF-8 mit BOM“) neu speichern.

**Nach dem Login: „Diese Seite funktioniert nicht — zu oft weitergeleitet“**

Meist kann die Weboberfläche die Trading-Datenbank nicht erreichen. In `storage\logs\laravel.log`
nach `ERROR` suchen. Häufige Auslöser: `TRADING_DB_USERNAME` oder `TRADING_DB_PASSWORD` in der
`.env` falsch, oder für den Benutzer gibt es in keinem Environment Tabellen — dann
`reset_IBKR_DB.py` mit genau dem Präfix ausführen, der beim Anlegen des Benutzers angegeben wurde
([TradingJournal-Weaver installieren](40-weaver-installieren.md), Schritt 4).

## 3. Daten abholen (Mail und Web-API)

**Es werden keine Berichte aus dem Postfach geholt**

- IBKR schickt die Berichte **nur an die E-Mail-Adresse, die beim Anlegen des IBKR-Kontos
  hinterlegt wurde**. `IMAP_USERNAME` in der `.env` muss genau dieses Postfach sein (oder eines,
  in das weitergeleitet wird).
- Gelesen wird nur der **Posteingang**. Verschiebt eine Filterregel die IBKR-Mails in einen
  anderen Ordner, findet der Abruf sie nicht.
- Im Protokoll steht „IMAP_USERNAME/IMAP_PASSWORD nicht konfiguriert oder noch auf
  Platzhalterwert“: Die Zugangsdaten in der `.env` sind leer oder noch die Vorlage.

**Web-API: „NameResolutionError … Failed to resolve 'gdcdyn.interactivebrokers.com'“**

Kein IBKR-Problem, sondern ein Namensauflösungs-Fehler (DNS) im eigenen Netz — häufig an
Handy-Hotspots oder kleinen Routern. Der Mail-Abruf ist davon nicht betroffen. Lösung: feste
DNS-Server eintragen.

PowerShell **als Administrator** (`WLAN` durch den Namen der eigenen Netzwerkverbindung ersetzen):

```powershell
Set-DnsClientServerAddress -InterfaceAlias "WLAN" -ServerAddresses 1.1.1.1, 8.8.8.8
ipconfig /flushdns
```

Rückgängig machen mit `Set-DnsClientServerAddress -InterfaceAlias "WLAN" -ResetServerAddresses`.

Die Einstellung bleibt bei Netzwechsel und Neustart erhalten, gilt aber nur für diese eine
Netzwerkverbindung (WLAN und Netzwerkkabel getrennt). Kommt der Fehler wieder, zuerst prüfen, ob
sie noch gesetzt ist — PowerShell (ohne Administrator):

```powershell
Get-DnsClientServerAddress -InterfaceAlias "WLAN" -AddressFamily IPv4
```

Steht dort nicht `1.1.1.1, 8.8.8.8`, die Einstellung erneut setzen. Erscheint in einem offenen
WLAN (Hotel, Bahn) die Anmeldeseite nicht, die Einstellung kurz zurücksetzen, anmelden und danach
wieder setzen.

**Web-API: Fehler 1025 („Too many failed attempts“)**

IBKR sperrt den Abruf vorübergehend, wenn kurz hintereinander zu viele fehlgeschlagene
Anfragen kommen. Den Abruf dann **nicht** wiederholt neu starten — das verlängert die Sperre.
Einige Zeit warten und vorher prüfen, ob Prüfcode (Token) und Query-ID in `IBKR_FLEX_QUERIES`
stimmen. Die Daten kommen in der Zwischenzeit weiter per Mail.

**Web-API: „Daten noch nicht verfügbar nach 5 Versuchen“**

IBKR erstellt den Bericht noch. Das kommt kurz nach Handelsschluss vor; einfach später erneut
abrufen.

## 4. Import

**Trades fehlen — im Protokoll: „Unbekannte accountId '…' in … — übersprungen“**

Das Konto ist in `accounts.toml` nicht eingetragen. Die Zuordnung läuft über die **letzten vier
Ziffern** der IBKR-Kontonummer. Nach dem Eintragen den Import erneut laufen lassen; die
übersprungenen Dateien liegen noch im Eingangsordner.

**Im Protokoll: „Konnte Datum nicht parsen: …“**

Die Flex Query verwendet ein anderes Datumsformat. Pflicht ist `dd/MM/yyyy`, Zeit `HHmmss`,
Trennzeichen `;` (Kapitel [IBKR einrichten](20-ibkr-einrichten.md), allgemeine
Konfiguration).

**Kontostand, Rendite und Max Drawdown bleiben leer („Keine NAV-Daten vorhanden“)**

Diese Werte kommen ausschließlich aus dem täglichen **Kontoauszug (CSV)**, nicht aus der Flex
Query. Prüfen:

- Ist der Kontoauszug bei IBKR eingerichtet und wird er per Mail zugestellt?
- Ist als **Sprache English** eingestellt? Der Import erkennt die Abschnitte an ihren englischen
  Bezeichnungen.
- Steht im Protokoll „accountId '…' nicht in accounts.toml — übersprungen“? Dann fehlt das
  Konto in `accounts.toml` (wie oben).

## 5. Anzeige im Journal

**Neue Trades sind nicht zu sehen**

Der Reihe nach prüfen:

1. Ist die Pipeline seit dem Trade gelaufen? IBKR erstellt die Berichte erst nach
   Handelsschluss — ein bis zwei Tage Nachlauf sind normal.
2. Ist oben das richtige **Environment** gewählt?
3. Schließt der **Zeitraum**-Filter den Trade aus? Testweise auf „Alle“ stellen.
4. Steht der Trade unter **Raw Data**? Wenn nicht, liegt das Problem beim Abholen oder Import
   (Abschnitte 3 und 4).

**Eine Position bleibt offen, obwohl sie bei IBKR geschlossen ist**

Der schließende Trade ist nie angekommen, etwa weil an diesem Tag weder Mail noch Web-API
geliefert haben. Zuerst unter **Raw Data** nachsehen. Fehlt der Trade dort, den Bericht für den
betreffenden Tag erneut abrufen. Für endgültig liegengebliebene Positionen gibt es ein
Wartungsskript ([Alltag mit dem TradingJournal](70-alltag.md), Abschnitt 4 „Eine Position
bleibt offen, obwohl sie geschlossen ist“).

**Warum weichen die Gewinne vom IBKR-Kontoauszug ab?**

Das Journal zeigt P&L überall **brutto** (ohne Kommissionen) und den **Netto**-Wert darunter.
Für den Vergleich mit IBKR den Netto-Wert verwenden.
