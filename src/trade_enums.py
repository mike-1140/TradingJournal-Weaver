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
