from enum import Enum


class AssetCategory(str, Enum):
    STOCK  = "STK"
    OPTION = "OPT"
    CASH   = "CASH"


class TransactionType(str, Enum):
    EXCH_TRADE = "ExchTrade"
    BOOK_TRADE = "BookTrade"


class BuySell(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"


class TradeStatus(str, Enum):
    OPEN         = "OPEN"
    REV_OPEN     = "REV_OPEN"
    SPLIT_REST   = "SPLIT_REST"
    PENDING      = "PENDING"
    CLOSED       = "Closed"
    EXPIRED      = "Expired"
    ASSIGNED     = "Assigned"
    CASH_SETTLED = "CashSettled"


class CampaignStatus(str, Enum):
    ACTIVE  = "ACTIVE"
    PENDING = "PENDING"
    CLOSED  = "CLOSED"


class LedgerAction(str, Enum):
    # --- Aktien: Eröffnung ---
    STK_BUY          = "STK_BUY"           # Kauf (Long-Einstieg)
    STK_SELL         = "STK_SELL"          # Leerverkauf (Short-Einstieg)
    # --- Aktien: Schließung ---
    STK_SELL_CLOSE   = "STK_SELL_CLOSE"    # Verkauf (Long schließen)
    STK_BUY_CLOSE    = "STK_BUY_CLOSE"     # Eindeckung (Short schließen)
    STK_SELL_PARTIAL = "STK_SELL_PARTIAL"  # Teilverkauf (Long, Rest verbleibt)
    STK_BUY_PARTIAL  = "STK_BUY_PARTIAL"   # Teileindeckung (Short, Rest verbleibt)
    # --- Optionen: Eröffnung ---
    OPT_PUT_SELL  = "OPT_PUT_SELL"         # Put verkaufen (Wheel-Einstieg)
    OPT_PUT_BUY   = "OPT_PUT_BUY"          # Put kaufen (Long Put)
    OPT_CALL_SELL = "OPT_CALL_SELL"        # Call verkaufen (Covered Call)
    OPT_CALL_BUY  = "OPT_CALL_BUY"         # Call kaufen (Long Call)
    # --- Optionen: Schließung ---
    OPT_PUT_BUY_CLOSE    = "OPT_PUT_BUY_CLOSE"      # Zurückkaufen (Short Put schließen)
    OPT_PUT_SELL_CLOSE   = "OPT_PUT_SELL_CLOSE"     # Verkaufen (Long Put schließen)
    OPT_CALL_BUY_CLOSE   = "OPT_CALL_BUY_CLOSE"     # Zurückkaufen (Short Call schließen)
    OPT_CALL_SELL_CLOSE  = "OPT_CALL_SELL_CLOSE"    # Verkaufen (Long Call schließen)
    OPT_PUT_BUY_PARTIAL  = "OPT_PUT_BUY_PARTIAL"    # Teilschließung Short Put
    OPT_PUT_SELL_PARTIAL = "OPT_PUT_SELL_PARTIAL"   # Teilschließung Long Put
    OPT_CALL_BUY_PARTIAL = "OPT_CALL_BUY_PARTIAL"   # Teilschließung Short Call
    OPT_CALL_SELL_PARTIAL = "OPT_CALL_SELL_PARTIAL" # Teilschließung Long Call
    # --- Options-Events ---
    OPTION_EXPIRATION = "OPTION_EXPIRATION"  # Option wertlos verfallen
    OPTION_EXERCISE   = "OPTION_EXERCISE"    # Ausübung / Assignment
    CASH_SETTLEMENT   = "CASH_SETTLEMENT"    # Barausgleich
    # --- Sonstiges ---
    TRADE_REVERSAL_OPEN = "TRADE_REVERSAL_OPEN"  # Reversal nach Richtungswechsel
    STOCK_SPLIT         = "STOCK_SPLIT"           # Aktien-Split / Reverse Split
