# Aufbau einer Flex Query

Dieses Kapitel zeigt, wie eine von IBKR gelieferte Flex Query (XML) aufgebaut ist und welche
Felder der Import (`import_ibkr_trades.py` → `flex_parser.py` → `day_trade_processor.py`)
daraus liest. Wie die Query im Kundenportal eingerichtet wird, beschreibt das Benutzerhandbuch
im Kapitel [IBKR einrichten](../benutzer/20-ibkr-einrichten.md).

---

## 1. Beispiel

Ein gekürztes Beispiel mit je einem Eintrag pro Abschnitt: ein Aktienkauf, ein verfallener
Short Put und ein Reverse Split. **Alle Werte sind erfunden.** Echte Dateien enthalten pro
Eintrag deutlich mehr Attribute (bei „Alle auswählen“: 84 je `Trade`, 44 je `OptionEAE`, 46 je
`CorporateAction`) — hier stehen nur die, die der Import auswertet, plus einige zur
Orientierung.

```xml
<FlexQueryResponse queryName="money_report" type="AF">
  <FlexStatements count="1">
    <FlexStatement accountId="U1234567" fromDate="10/03/2026" toDate="17/03/2026"
                   period="LastNCalendarDays" whenGenerated="18/03/2026;061502">

      <Trades>
        <Trade accountId="U1234567" currency="USD" fxRateToBase="0.9174"
               assetCategory="STK" subCategory="COMMON" symbol="AAPL"
               description="APPLE INC" conid="265598" isin="US0378331005"
               tradeID="7012345678" dateTime="16/03/2026;153012"
               transactionType="ExchTrade" buySell="BUY" quantity="100"
               tradePrice="212.5" proceeds="-21250" ibCommission="-1"
               netCash="-21251" openCloseIndicator="O" fifoPnlRealized="0"
               ibOrderID="4401234567" orderReference="" multiplier="1"
               putCall="" strike="" expiry="" underlyingConid="" underlyingSymbol="" />
      </Trades>

      <OptionEAE>
        <OptionEAE accountId="U1234567" currency="USD" fxRateToBase="0.9174"
                   assetCategory="OPT" subCategory="P" symbol="XYZ   260313P00040000"
                   description="XYZ 13MAR26 40 P" conid="801234567"
                   underlyingConid="45678901" underlyingSymbol="XYZ"
                   multiplier="100" strike="40" expiry="13/03/2026" putCall="P"
                   date="13/03/2026" transactionType="Expiration"
                   quantity="1" tradePrice="0" proceeds="0" tradeID="7012340000" />
      </OptionEAE>

      <CorporateActions>
        <CorporateAction accountId="U1234567" currency="USD" fxRateToBase="0.9174"
                         assetCategory="STK" symbol="XYZ" conid="45678901"
                         description="XYZ(US0000000000) SPLIT 1 FOR 25"
                         reportDate="12/03/2026" dateTime="11/03/2026;202500"
                         type="RS" quantity="-96" proceeds="0" actionID="150123456" />
      </CorporateActions>

    </FlexStatement>
  </FlexStatements>
</FlexQueryResponse>
```

**Aufbau in Kürze:**

- Eine Datei enthält ein oder mehrere `FlexStatement`-Elemente — **eines je Konto**.
  `accountId` am `FlexStatement` bestimmt, welchem Benutzer und Environment die Daten zugeordnet
  werden (`accounts.toml`, Schlüssel = letzte vier Ziffern).
- Die drei Abschnitte entsprechen den drei in der Query aktivierten Sektionen. Das Container-
  und das Eintragselement heißen bei den Options-Ereignissen beide `OptionEAE`.
- Datum mit Uhrzeit hat das Format `dd/MM/yyyy;HHmmss` (z. B. `16/03/2026;153012`), reine
  Datumsfelder `dd/MM/yyyy`. Ein anderes in der Query eingestelltes Format kann der Import nicht
  lesen (`parse_datetime_flex()` in `src/utils/div_utils.py`).
- Leere Attribute (`strike=""` bei Aktien) sind normal — IBKR schreibt jedes ausgewählte Feld,
  auch wenn es für den Eintrag keinen Wert hat.

## 2. Welche Felder der Import liest

### `Trade` (`extract_trades_for_db`)

| Gruppe | Felder |
|---|---|
| Identität | `tradeID`, `ibOrderID`, `orderReference`, `transactionType` |
| Instrument | `assetCategory`, `subCategory`, `symbol`, `description`, `conid`, `isin`, `currency` |
| Optionen | `putCall`, `strike`, `expiry`, `multiplier`, `underlyingConid`, `underlyingSymbol` |
| Ausführung | `dateTime`, `buySell`, `quantity`, `tradePrice`, `openCloseIndicator` |
| Geld | `proceeds`, `netCash`, `ibCommission`, `fxRateToBase`, `fifoPnlRealized` |

`ibOrderID` ist doppelt wichtig: Er bündelt Teilausführungen derselben Order und erkennt
Mehrbein-Strategien (Spreads, Iron Condors), die IBKR als einzelne Trades liefert.
Reine Devisentausch-Trades (`assetCategory="CASH"`, `symbol="EUR.USD"`) werden in zwei Zeilen
(Basis- und Gegenwährung) zerlegt.

### `OptionEAE` (`extract_optioneae_for_db`)

`transactionType` (`Expiration`, `Exercise`, `Assignment`, `CashSettlement`), `date`, `tradeID`,
`conid`, `symbol`, `description`, `assetCategory`, `subCategory`, `putCall`, `strike`, `expiry`,
`multiplier`, `underlyingConid`, `underlyingSymbol`, `quantity`, `proceeds`, `currency`,
`fxRateToBase`, `isin`.

Diese Einträge beschreiben das *Ereignis*. Die zugehörige Buchung liefert IBKR zusätzlich als
automatischen Trade im Abschnitt `Trades`; `book_trades.py` verbindet beide über `tradeID` bzw.
`conid` + Datum und überträgt den Status (*Expired*, *Assigned*, *Exercised*, *CashSettled*).

### `CorporateAction` (`extract_corporateaction_for_db`)

`type` (z. B. `RS` = Reverse Split, `FS`/`SS` = Split), `actionID`, `reportDate`, `description`,
`symbol`, `conid`, `isin`, `assetCategory`, `subCategory`, `quantity`, `proceeds`, `currency`,
`fxRateToBase`, `multiplier`, `underlyingConid`, `underlyingSymbol`.

Aus Splits passt die Verarbeitung Menge und Einstandspreis aller offenen Tranchen an (siehe
[Architektur und Pipeline](10-architektur-und-pipeline.md), Fall SPLIT).

## 3. Mail- und API-Query

Die per E-Mail zugestellte und die per Web-API abgerufene Query sind **gleich aufgebaut**,
sofern sie mit denselben Sektionen eingerichtet sind. Der Import behandelt beide Ordner
(`incoming_mail\`, `incoming_api\`) gleich; doppelt gelieferte Trades erkennt er an einer
Prüfsumme (`tradeID`, `dateTime`, `symbol`, `quantity`, `tradePrice`).

Snapshot-Daten (Kontostand, Cash, Rendite) enthalten die Flex Queries nicht — sie kommen
ausschließlich aus dem täglichen Kontoauszug (CSV per Mail), siehe
[Architektur und Pipeline](10-architektur-und-pipeline.md), § 8.2 `account_snapshots`.
