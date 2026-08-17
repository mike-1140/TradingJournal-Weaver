# tools/demo/close_expired_open_options.py
#
# Erzeugt eine synthetische FlexQuery-XML-Datei, die jede noch offene
# (processed=0) Options-/FOP-Position der Demo-DB mit bereits verstrichenem
# Expiry-Datum als wertlosen Verfall schließt — im exakt gleichen XML-Format
# wie ein echtes IBKR-BookTrade-Verfalls-Ereignis (transactionType="BookTrade",
# openCloseIndicator="C", notes="Ep"), damit die Datei ganz normal durch
# import_ibkr_trades.py + process_ibkr_trades.py läuft und trades_close,
# campaign_ledger sowie der Kampagnen-Status vom bestehenden, getesteten
# Code-Pfad korrekt aktualisiert werden — keine manuellen SQL-Inserts.
#
# Aktien bleiben bewusst unangetastet (reale Depots haben zu jedem Zeitpunkt
# offene Aktienpositionen, das ist normal — bei Optionen mit verstrichenem
# Expiry ist "noch offen" dagegen immer ein Datenlücken-Artefakt).
#
# Nicht idempotent nötig: läuft NACH dem normalen Import+Process-Lauf gegen
# den aktuellen DB-Stand, erzeugt pro Lauf nur für die dann noch offenen
# Positionen einen Schließungs-Trade. Nach dem Einspielen sind sie processed=1
# und tauchen beim nächsten Lauf nicht mehr auf.
#
# Verwendung (nach dem normalen Demo-Import+Process, siehe README):
#   $env:DB_NAME_TEST = "ibkr_demo"
#   .venv\Scripts\python -m tools.demo.close_expired_open_options
#   Copy-Item input\demo_source\flex.demo_close_expired_options.xml C:\Trade_XML\incoming_mail\
#   .venv\Scripts\python -m src.import_ibkr_trades test demo_
#   .venv\Scripts\python -m src.process_ibkr_trades test demo_
#   (bei Bedarf wiederholen, falls die neu geschlossenen Positionen wiederum
#   Kampagnen mit anderen, noch offenen Legs betreffen — üblicherweise reicht 1x)

import sys
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import quoteattr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import create_engine, text

from src.config import get_db_url
from src.utils.path_utils import get_project_root

ENV = "TEST"
PREFIX = "demo_"
FAKE_ACCOUNT_ID = "DU0009999"
OUTPUT_FILE = get_project_root() / "input" / "demo_source" / "flex.demo_close_expired_options.xml"

# IBKR-Format DD/MM/YYYY;HHMMSS — 16:20 Uhr ist die reale Standard-Verfallszeit
# in den echten FlexQuery-Fixtures (siehe z.B. OMEX-Expirations).
EXPIRY_TIME = "162000"


def _attr(name: str, value) -> str:
    return f"{name}={quoteattr(str(value))}"


def build_close_trade_xml(row: dict, synthetic_id: int) -> str:
    expiry_date: date = row["expiry"].date() if hasattr(row["expiry"], "date") else row["expiry"]
    date_str = expiry_date.strftime("%d/%m/%Y")
    date_time_str = f"{date_str};{EXPIRY_TIME}"

    close_quantity = -float(row["quantity"])
    close_buy_sell = "SELL" if row["buySell"] == "BUY" else "BUY"
    original_net_cash = float(row["netCash"])

    fields = {
        "accountId": FAKE_ACCOUNT_ID,
        "acctAlias": "",
        "model": "",
        "currency": row["currency"] or "USD",
        "fxRateToBase": row["fxRateToBase"] or 1,
        "assetCategory": row["assetCategory"],
        "subCategory": row["subCategory"] or "",
        "symbol": row["symbol"],
        "description": row["description"] or "",
        "conid": row["conid"] or "",
        "securityID": "", "securityIDType": "", "cusip": "", "isin": "", "figi": "",
        "listingExchange": "",
        "underlyingConid": row["underlyingConid"] or "",
        "underlyingSymbol": row["underlyingSymbol"] or "",
        "underlyingSecurityID": "", "underlyingListingExchange": "",
        "issuer": "", "issuerCountryCode": "",
        "tradeID": 999000000 + synthetic_id,
        "multiplier": row["multiplier"] or 100,
        "relatedTradeID": "",
        "strike": row["strike"] or "",
        "reportDate": date_str,
        "expiry": date_str,
        "dateTime": date_time_str,
        "putCall": row["putCall"] or "",
        "tradeDate": date_str,
        "principalAdjustFactor": "",
        "settleDateTarget": date_str,
        "transactionType": "BookTrade",
        "exchange": "--",
        "quantity": close_quantity,
        "tradePrice": 0,
        "tradeMoney": 0,
        "proceeds": 0,
        "taxes": 0,
        "ibCommission": 0,
        "ibCommissionCurrency": row["currency"] or "USD",
        "netCash": 0,
        "closePrice": 0,
        "openCloseIndicator": "C",
        "notes": "Ep",
        "cost": original_net_cash,
        "fifoPnlRealized": original_net_cash,
        "mtmPnl": 0,
        "origTradePrice": 0, "origTradeDate": "", "origTradeID": "", "origOrderID": 0, "origTransactionID": 0,
        "buySell": close_buy_sell,
        "clearingFirmID": "",
        "ibOrderID": 999000000 + synthetic_id,
        "transactionID": 999000000 + synthetic_id,
        "ibExecID": "", "relatedTransactionID": "", "rtn": "", "brokerageOrderID": "",
        "orderReference": "", "volatilityOrderLink": "", "exchOrderId": "N/A", "extExecID": "N/A",
        "orderTime": "", "openDateTime": "", "holdingPeriodDateTime": "", "whenRealized": "", "whenReopened": "",
        "levelOfDetail": "EXECUTION",
        "changeInPrice": 0, "changeInQuantity": 0, "orderType": "",
        "traderID": "", "isAPIOrder": "N", "accruedInt": 0, "initialInvestment": "",
        "serialNumber": "", "deliveryType": "", "commodityType": "", "fineness": "0.0", "weight": "0.0",
        "positionActionID": "",
    }

    attrs = " ".join(_attr(k, v) for k, v in fields.items())
    return f"<Trade {attrs} />"


def build_option_eae_xml(row: dict, synthetic_id: int) -> str:
    """
    Ohne dieses Element bleibt trades_close.status/closedBy bei "Closed"/"SELL" statt
    "Expired"/"EXPIRY" — book_trades.py setzt status="Expired" nur, wenn ein passendes
    <OptionEAE transactionType="Expiration"> mit derselben tradeID im selben
    FlexStatement existiert (siehe book_trades.py Fall 3 "SPX - Expired Option").
    Rein kosmetisch (P&L/offen-geschlossen ist bereits ohne dieses Element korrekt),
    aber macht die Demo-Detailseiten konsistent mit echten IBKR-Verfallsdaten.
    """
    expiry_date: date = row["expiry"].date() if hasattr(row["expiry"], "date") else row["expiry"]
    date_str = expiry_date.strftime("%d/%m/%Y")
    close_quantity = -float(row["quantity"])
    original_net_cash = float(row["netCash"])

    fields = {
        "accountId": FAKE_ACCOUNT_ID, "acctAlias": "", "model": "",
        "currency": row["currency"] or "USD",
        "fxRateToBase": row["fxRateToBase"] or 1,
        "assetCategory": row["assetCategory"],
        "subCategory": row["subCategory"] or "",
        "symbol": row["symbol"],
        "description": row["description"] or "",
        "conid": row["conid"] or "",
        "securityID": "", "securityIDType": "", "cusip": "", "isin": "", "figi": "",
        "listingExchange": "",
        "underlyingConid": row["underlyingConid"] or "",
        "underlyingSymbol": row["underlyingSymbol"] or "",
        "underlyingSecurityID": "", "underlyingListingExchange": "",
        "issuer": "", "issuerCountryCode": "",
        "multiplier": row["multiplier"] or 100,
        "strike": row["strike"] or "",
        "expiry": date_str,
        "putCall": row["putCall"] or "",
        "principalAdjustFactor": "",
        "date": date_str,
        "transactionType": "Expiration",
        "quantity": close_quantity,
        "tradePrice": 0, "markPrice": 0, "proceeds": 0, "commisionsAndTax": 0,
        "costBasis": original_net_cash,
        "realizedPnl": original_net_cash,
        "fxPnl": 0, "mtmPnl": 0,
        "tradeID": 999000000 + synthetic_id,
        "serialNumber": "", "deliveryType": "", "commodityType": "",
        "fineness": "0.0", "weight": "0.0",
    }
    attrs = " ".join(_attr(k, v) for k, v in fields.items())
    return f"<OptionEAE {attrs} />"


def build_flex_statement(trade_xml: str, eae_xml: str, expiry_date: date) -> str:
    date_str = expiry_date.strftime("%d/%m/%Y")
    when_generated = datetime.now().strftime("%d/%m/%Y;%H%M%S")
    return (
        f'<FlexStatement accountId="{FAKE_ACCOUNT_ID}" fromDate="{date_str}" toDate="{date_str}" '
        f'period="" whenGenerated="{when_generated}">\n'
        f"<Trades>\n{trade_xml}\n</Trades>\n"
        f"<OptionEAE>\n{eae_xml}\n</OptionEAE>\n"
        f"<CorporateActions> </CorporateActions>\n"
        f"</FlexStatement>"
    )


def main() -> None:
    db_url = get_db_url("test")
    engine = create_engine(db_url)

    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT id, symID, assetCategory, subCategory, symbol, description, underlyingSymbol,
                   conid, underlyingConid, quantity, expiry, buySell, putCall, strike, multiplier,
                   dateTime, tradePrice, netCash, proceeds, ibCommission, currency, fxRateToBase
            FROM `{PREFIX}trades_open`
            WHERE environment = :env AND processed = 0
              AND assetCategory IN ('OPT', 'FOP')
              AND expiry < CURDATE()
            ORDER BY expiry
        """), {"env": ENV}).mappings().all()

    print("=" * 65)
    print("  CLOSE EXPIRED OPEN OPTIONS (Demo)")
    print("=" * 65)
    print(f"  Gefundene verwaiste Optionspositionen: {len(rows)}")

    if not rows:
        print("  Nichts zu tun — keine Datei erzeugt.")
        return

    statements = []
    for i, row in enumerate(rows, start=1):
        trade_xml = build_close_trade_xml(row, i)
        eae_xml = build_option_eae_xml(row, i)
        expiry_date = row["expiry"].date() if hasattr(row["expiry"], "date") else row["expiry"]
        statements.append(build_flex_statement(trade_xml, eae_xml, expiry_date))
        print(f"    #{row['id']:<5} {row['symbol']:<24} expiry {expiry_date}")

    xml = (
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        '<FlexQueryResponse queryName="demo_close_expired" type="AF">\n'
        f'<FlexStatements count="{len(statements)}">\n\n'
        + "\n\n".join(statements)
        + "\n\n</FlexStatements>\n</FlexQueryResponse>\n"
    )

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(xml, encoding="utf-8")

    print()
    print(f"  Geschrieben: {OUTPUT_FILE}")
    print(f"  Naechster Schritt: Datei nach incoming_mail kopieren, dann")
    print(f"  import_ibkr_trades.py + process_ibkr_trades.py erneut laufen lassen.")
    print("=" * 65)


if __name__ == "__main__":
    main()
