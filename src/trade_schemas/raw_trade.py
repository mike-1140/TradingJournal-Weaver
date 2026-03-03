# trade_schemas/raw_trade.py

# from typing import Dict, Any, List
# from datetime import datetime
from .base_schema import BaseSchema
from src.logger_setup import setup_logging
from src.utils.path_utils import get_project_root
from src.config import TABLE_TRADES_RAW

# Get logger - use the same logger name across all files
log_file = get_project_root() / "log/app.log"
logger, _ = setup_logging('my_app', level="simple", log_file=log_file)


class RawTradeSchema(BaseSchema):
    FIELDS = [
        'gid',
        'assetCategory',
        'subCategory',
        'symbol',
        'description',
        'underlyingSymbol',
        'underlyingConid',
        'conid',
        'multiplier',
        'strike',
        'expiry',
        'putCall',
        'buySell',
        'dateTime',
        'quantity',
        'tradePrice',
        'netCash',
        'proceeds',
        'ibCommission',
        'currency',
        'fxRateToBase',
        'fifoPnlRealized',
        'openCloseIndicator',
        'strategy',
        'status',
        'tradeID',
        'checksum',
        'processed'
    ]

    REQUIRED_FIELDS = [
        'symbol',
        'quantity',
        'tradePrice',
        'dateTime',
        'tradeID'
    ]

    FIELD_MAPPINGS = {
        # 'assetClass': 'assetCategory',
        # 'price': 'tradePrice'
    }

    TABLE_NAME = TABLE_TRADES_RAW

    @classmethod
    def log_trade(cls, raw_trade):
        # Normalisiere die Daten vor dem Logging
        cls.normalize_date_fields(raw_trade)
        # spezial Logging für Split
        if raw_trade.get('tradeID') == -1:
            data_text = f"RS  "
        else:
            data_text = f"R   "

        if raw_trade['assetCategory'] == 'OPT':
            header_text = f"        id     | Symbol                | DateOpen   | B/S | Quantity | PriceOpen | NetCashOp | Strategy |"
        else:
            header_text = f"        id     | Symbol | DateOpen   | B/S | Quantity | PriceOpen | NetCashOp | Strategy |"

        logger.info(header_text)
        # Da wir die Daten bereits normalisiert haben, können wir sie direkt verwenden
        data_text_1 = (f"{fmt(raw_trade.get('tradeID'), 10)} | {fmt(raw_trade.get('symbol'), 6)} | "
                       f"{fmt(raw_trade.get('dateTime'), 8)} | "
                       f"{fmt(raw_trade.get('buySell'), 4)}| "
                       f"{fmt(raw_trade.get('quantity'), 8, 2)} | "
                       f"{fmt(raw_trade.get('tradePrice'), 9, 4)} | "
                       f"{fmt(raw_trade.get('netCash', 0), 9, 2)} | {fmt(raw_trade.get('strategy'), 8)} |")

        logger.info(data_text + data_text_1)
