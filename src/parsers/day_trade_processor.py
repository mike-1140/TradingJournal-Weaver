import pandas as pd
from src.utils.div_utils import to_decimal
from src.utils.div_utils import compute_checksum, parse_datetime_flex
from src.utils.corporate_utils import SPLIT_TYPES, get_split_info
import uuid


def extract_trades_for_db(stmt, logger):
    trades_data = []
    cashfx_table = []
    for elem in stmt.findall(".//Trade"):
        t = elem.attrib
        if t.get("assetCategory") == "CASH":
            base, quote = t.get("symbol").split(".")
            link_id = str(uuid.uuid4())

            # Eine Zeile pro Umtausch fuer trades_fx (Basis-/Zielwaehrung nebeneinander,
            # nicht als zwei synthetische from/to-Zeilen wie unten fuer trades_raw)
            cashfx_table.append({
                "assetCategory": t.get("assetCategory"),
                "tradeID": t.get("tradeID"),
                "ibOrderID": t.get("ibOrderID"),
                "symbol": t.get("symbol"),
                "baseCurrency": base,
                "quoteCurrency": quote,
                "baseAmount": to_decimal(t.get("quantity") or 0),
                "quoteAmount": to_decimal(t.get("proceeds") or 0),
                "fxRate": to_decimal(t.get("tradePrice") or 0),
                "commission": to_decimal(t.get("ibCommission") or 0),
                "dateTime": parse_datetime_flex(t.get("dateTime"), logger),
            })

            trades_data.append({
                "symID": None,
                "assetCategory": t.get("assetCategory"),
                "subCategory": t.get("subCategory"),
                "symbol": t.get("symbol"),
                "description": t.get("description"),
                "underlyingSymbol": t.get("underlyingSymbol"),
                "underlyingConid": t.get("underlyingConid"),
                "isin": t.get("isin"),
                "multiplier": to_decimal(t.get("multiplier") or 1),
                "strike": to_decimal(t.get("strike") or 0),
                "expiry": parse_datetime_flex(t.get("expiry")),
                "putCall": t.get("putCall"),
                "buySell": t.get("buySell"),
                "dateTime": parse_datetime_flex(t.get("dateTime"), logger),
                "quantity": to_decimal('1.0'),
                "tradePrice": to_decimal(t.get("tradePrice") or 0),
                "netCash": to_decimal(t.get("quantity") or 0),
                "proceeds": to_decimal('0.0'),
                "ibCommission": to_decimal(t.get("ibCommission") or 0),
                "fxRateToBase": to_decimal(t.get("fxRateToBase") or 1),
                "fifoPnlRealized": to_decimal('0.0'),
                "openCloseIndicator": None,
                "strategy": t.get("orderReference"),
                "status": None,
                "tradeID": t.get("tradeID"),
                "ibOrderID": t.get("ibOrderID"),
                "conid": t.get("conid"),
                "currency": base,
                "transactionType": t.get("transactionType"),
                "source": "trade",
                "is_split": False,
                "split_type": None,
                "actionID": 0,
                "linkID": link_id,
                "opt_strategy": 0,
                "opt_strategyName": "",  # Platzhalter für spätere Verknüpfung
                "opt_strategyID": "",  # Platzhalter für spätere Verknüpfung
                "checksum": None,
                "processed": 0,
            })
            tradeprice = to_decimal(t.get("tradePrice") or 0)
            if tradeprice != 0:
                tradeprice = 1 / tradeprice
            trades_data.append({
                "symID": None,
                "assetCategory": t.get("assetCategory"),
                "subCategory": t.get("subCategory"),
                "symbol": t.get("symbol"),
                "description": t.get("description"),
                "underlyingSymbol": t.get("underlyingSymbol"),
                "underlyingConid": t.get("underlyingConid"),
                "isin": t.get("isin"),
                "multiplier": to_decimal(t.get("multiplier") or 1),
                "strike": to_decimal(t.get("strike") or 0),
                "expiry": parse_datetime_flex(t.get("expiry")),
                "putCall": t.get("putCall"),
                "buySell": t.get("buySell"),
                "dateTime": parse_datetime_flex(t.get("dateTime"), logger),
                "quantity": to_decimal('2.0'),
                "tradePrice": tradeprice,
                "netCash": to_decimal(t.get("proceeds") or 0),
                "proceeds": to_decimal('0.0'),
                "ibCommission": to_decimal('0.0'),
                "fxRateToBase": to_decimal(t.get("fxRateToBase") or 1),
                "fifoPnlRealized": to_decimal('0.0'),
                "openCloseIndicator": None,
                "strategy": t.get("orderReference"),
                "status": None,
                "tradeID": t.get("tradeID"),
                "ibOrderID": t.get("ibOrderID"),
                "conid": t.get("conid"),
                "currency": quote,
                "transactionType": t.get("transactionType"),
                "source": "trade",
                "is_split": False,
                "split_type": None,
                "actionID": 0,
                "linkID": link_id,
                "opt_strategy": 0,
                "opt_strategyName": None,  # Platzhalter für spätere Verknüpfung
                "opt_strategyID": None,  # Platzhalter für spätere Verknüpfung
                "checksum": None,
                "processed": 0,
            })
        else:
            trades_data.append({
                "symID": None,
                "assetCategory": t.get("assetCategory"),
                "subCategory": t.get("subCategory"),
                "symbol": t.get("symbol"),
                "description": t.get("description"),
                "underlyingSymbol": t.get("underlyingSymbol"),
                "underlyingConid": t.get("underlyingConid"),
                "isin": t.get("isin"),
                "multiplier": to_decimal(t.get("multiplier") or 1),
                "strike": to_decimal(t.get("strike") or 0),
                "expiry": parse_datetime_flex(t.get("expiry")),
                "putCall": t.get("putCall"),
                "buySell": t.get("buySell"),
                "dateTime": parse_datetime_flex(t.get("dateTime"), logger),
                "quantity": to_decimal(t.get("quantity") or 0),
                "tradePrice": to_decimal(t.get("tradePrice") or 0),
                "netCash": to_decimal(t.get("netCash") or 0),
                "proceeds": to_decimal(t.get("proceeds") or 0),
                "ibCommission": to_decimal(t.get("ibCommission") or 0),
                "fxRateToBase": to_decimal(t.get("fxRateToBase") or 1),
                "fifoPnlRealized": to_decimal(t.get("fifoPnlRealized") or 0),
                "openCloseIndicator": t.get("openCloseIndicator"),
                "strategy": t.get("orderReference"),
                "status": None,
                "tradeID": t.get("tradeID"),
                "ibOrderID": t.get("ibOrderID"),
                "conid": t.get("conid"),
                "currency": t.get("currency"),
                "transactionType": t.get("transactionType"),
                "source": "trade",
                "is_split": False,
                "split_type": None,
                "actionID": 0,
                "linkID": "",
                "opt_strategy": 0,
                "opt_strategyName": "",  # Platzhalter für spätere Verknüpfung
                "opt_strategyID": "",  # Platzhalter für spätere Verknüpfung
                "checksum": None,
                "processed": 0,
            })

    return pd.DataFrame(trades_data) if trades_data else pd.DataFrame(), pd.DataFrame(
        cashfx_table) if cashfx_table else pd.DataFrame()


def extract_optioneae_for_db(stmt, logger):
    eae_data = []
    for elem in stmt.findall(".//OptionEAE"):
        e = elem.attrib
        eae_data.append({
            "symID": None,
            "assetCategory": e.get("assetCategory"),
            "subCategory": e.get("subCategory"),
            "symbol": e.get("symbol"),
            "description": e.get("description"),
            "underlyingSymbol": e.get("underlyingSymbol"),
            "underlyingConid": e.get("underlyingConid"),
            "isin": e.get("isin"),
            "multiplier": to_decimal(e.get("multiplier") or 1),
            "strike": to_decimal(e.get("strike") or 0),
            "expiry": parse_datetime_flex(e.get("expiry"), logger),
            "putCall": e.get("putCall"),
            "buySell": e.get("buySell"),
            # dateTime aus "date" Feld ableiten
            "dateTime": parse_datetime_flex(e.get("date"), logger),
            "quantity": to_decimal(e.get("quantity") or 0),
            "tradePrice": to_decimal('0.0'),
            "netCash": to_decimal(e.get("netCash") or 0),
            "proceeds": to_decimal(e.get("proceeds") or 0),
            "ibCommission": to_decimal('0.0'),
            "fxRateToBase": to_decimal(e.get("fxRateToBase") or 1),
            "fifoPnlRealized": to_decimal('0.0'),
            "strategy": None,
            "status": None,
            "tradeID": e.get("tradeID"),
            "ibOrderID": None,
            "conid": e.get("conid"),
            "currency": e.get("currency"),
            "transactionType": e.get("transactionType"),
            "source": "optioneae",
            "is_split": False,
            "split_type": None,
            "actionID": 0,
            "linkID": "",
            "opt_strategy": 0,
            "opt_strategyName": "",  # Platzhalter für spätere Verknüpfung
            "opt_strategyID": "",  # Platzhalter für spätere Verknüpfung
            "checksum": None,
            "processed": 0,
        })
    return pd.DataFrame(eae_data) if eae_data else pd.DataFrame()


def extract_corporateaction_for_db(stmt, logger):
    ca_data = []
    for elem in stmt.findall(".//CorporateAction"):
        c = elem.attrib
        ca_data.append({
            "symID": None,
            "assetCategory": c.get("assetCategory"),
            "subCategory": c.get("subCategory"),
            "symbol": c.get("symbol"),
            "description": c.get("description"),
            "underlyingSymbol": c.get("underlyingSymbol"),
            "underlyingConid": c.get("underlyingConid"),
            "isin": c.get("isin"),
            "multiplier": to_decimal(c.get("multiplier") or 1),
            "strike": to_decimal('0.0'),
            "expiry": None,
            "putCall": None,
            "buySell": None,
            "dateTime": parse_datetime_flex(c.get("reportDate"), logger),
            "quantity": to_decimal(c.get("quantity") or 0),
            "tradePrice": to_decimal('0.0'),
            "netCash": to_decimal(c.get("netCash") or 0),  # meist 0 bei Splits
            "proceeds": to_decimal(c.get("proceeds") or 0),
            "ibCommission": to_decimal('0.0'),
            "fxRateToBase": to_decimal(c.get("fxRateToBase") or 1),
            "fifoPnlRealized": to_decimal('0.0'),
            "strategy": None,
            "status": None,
            "tradeID": c.get("tradeID"),
            "ibOrderID": None,
            "conid": c.get("conid"),
            "currency": c.get("currency"),
            "transactionType": c.get("type"),
            "source": "split",
            "is_split": c.get("type") in SPLIT_TYPES,
            "split_type": get_split_info(c.get("type")),
            # "is_split": c.get("type") in ["RS", "SS", "FS"],  # "Split", "Reverse Split", "Forward Split"
            # "split_type": c.get("type") if c.get("type") in ["RS", "SS", "FS"] else None,
            "actionID": c.get("actionID"),
            "linkID": "",
            "opt_strategy": 0,
            "opt_strategyName": "",  # Platzhalter für spätere Verknüpfung
            "opt_strategyID": "",  # Platzhalter für spätere Verknüpfung
            "checksum": None,
            "processed": 0
        })
    return pd.DataFrame(ca_data) if ca_data else pd.DataFrame()


def process_day_trades(df_day: pd.DataFrame, logger) -> None:
    """
    Verarbeitet alle Trades eines einzelnen FlexStatements (Tages- oder Kontoabschnitts).
    Enthält:
      - Zuordnung Booktrades
      - Erkennung Expired/Assigned
      - FX & Cash Settl.
      - CorporateActions
    """

    logger.info(f"🔄 Starte Tagesverarbeitung: {len(df_day)} Trades")

    if df_day.empty:
        logger.debug("Keine Trades vorhanden — übersprungen.")
        return

    # --- 1️⃣ Grundlegende Normalisierung ---
    df_day = df_day.copy()
    df_day.columns = df_day.columns.str.lower()
    df_day["assetCategory"] = df_day["assetCategory"].str.upper()
    df_day["symbol"] = df_day["symbol"].str.upper()

    # --- 2️⃣ Gruppierung: nach Asset-Kategorie ---
    for category, df_cat in df_day.groupby("assetCategory", dropna=False):
        logger.info(f"📂 Kategorie: {category}, {len(df_cat)} Trades")

        if category in {"STK", "OPT", "FUT"}:
            handle_equity_or_derivative(df_cat, logger)
        elif category == "CASH":
            handle_cash_settlements(df_cat, logger)
        elif category == "FX":
            handle_fx_trades(df_cat, logger)
        elif category in {"CASH REPORT", "CORPORATE"}:
            handle_corporate_actions(df_cat, logger)
        else:
            logger.warning(f"⚠️ Unbekannte Asset-Kategorie: {category}")


# === Handler-Funktionen =============================================

def handle_equity_or_derivative(df, logger):
    """
    Verarbeitet STK/OPT/FUT Trades – inkl. Booktrades, Expiry & Assignment.
    """
    # 1. Booktrades (Transfers zwischen Konten)
    df_books = df[df["tradeType"].str.contains("BOOK", case=False, na=False)]
    if not df_books.empty:
        logger.info(f"🔁 {len(df_books)} Booktrades erkannt – werden separat gespeichert.")
        df_books["checksum"] = df_books.apply(compute_checksum, axis=1)
        # db.safe_write_dataframe(df_books, "trades_book")

    # 2. Expiry & Assignment erkennen
    df_expired = df[df["tradeType"].str.contains("EXPIRE|ASSIGN", case=False, na=False)]
    if not df_expired.empty:
        logger.info(f"⌛ {len(df_expired)} Expired/Assigned Trades erkannt.")
        # db.safe_write_dataframe(df_expired, TABLE_TRADES_CLOSE)

    # 3. Normale Öffnungen & Schließungen
    df_active = df[
        ~df["tradeType"].str.contains("BOOK|EXPIRE|ASSIGN", case=False, na=False)
    ]
    if not df_active.empty:
        pass
        # Hier könnte Logik kommen, um offene Positionen zu matchen
        # db.safe_write_dataframe(df_active, TABLE_TRADES_OPEN)


def handle_fx_trades(df, logger):
    """
    Verarbeitet FX-Trades (Devisen).
    """
    logger.info(f"💱 {len(df)} FX-Trades erkannt.")
    df["checksum"] = df.apply(compute_checksum, axis=1)
    # db.safe_write_dataframe(df, TABLE_TRADES_FX)


def handle_cash_settlements(df, logger):
    """
    Verarbeitet Cash-Settlments (Zinsen, Gebühren, Dividenden etc.).
    """
    logger.info(f"💰 {len(df)} Cash-Settlments erkannt.")
    df["checksum"] = df.apply(compute_checksum, axis=1)
    # db.safe_write_dataframe(df, TABLE_TRADES_CASH)


def handle_corporate_actions(df, logger):
    """
    Behandelt Corporate Actions wie Stock Splits oder Merger.
    """
    logger.info(f"🏢 {len(df)} Corporate Actions erkannt.")
    df["checksum"] = df.apply(compute_checksum, axis=1)
    # db.safe_write_dataframe(df, "trades_corporate")
