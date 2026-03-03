# trade_schemas/closed_trade.py

from typing import Dict, Any, List
from datetime import datetime, date
from .base_schema import BaseSchema
from src.logger_setup import setup_logging, format_header, format_row, print_log
from src.utils.path_utils import get_project_root
from src.config import TABLE_TRADES_CLOSE

BOX_HEAVY_VERTICAL = '\u2503'  # ┃
BOX_HEAVY_UP_AND_RIGHT = '\u2517'  # ┗
BOX_HEAVY_VERTICAL_AND_RIGHT = '\u2523'  # ┣

# Get logger - use the same logger name across all files
log_file = get_project_root() / "log/app.log"
logger, _ = setup_logging('my_app', level="simple", log_file=log_file)

close_columns = [
    {"label": "id", "key": "tradeID", "width": 12},
    {"label": "Symbol", "key": "symbol", "width": 6},
    {"label": "DateClose", "key": "dateTimeClose", "width": 17},
    {"label": "B/S", "key": "buySellClose", "width": 4},
    {"label": "Quantity", "key": "quantity", "width": 8, "precision": 2},
    {"label": "PriceClose", "key": "tradePriceClose", "width": 9, "precision": 2},
    {"label": "NetCashCl", "key": "netCashClose", "width": 9, "precision": 2},
    # {"label": "Strategy", "key": "strategy", "width": 8},
    {"label": "Profit", "key": "profit", "width": 9, "precision": 2},
]
close_columns_opt = [
    {"label": "id", "key": "tradeID", "width": 12},
    {"label": "Symbol", "key": "description", "width": 19},
    {"label": "DateClose", "key": "dateTimeClose", "width": 17},
    {"label": "B/S", "key": "buySellClose", "width": 4},
    {"label": "Quantity", "key": "quantity", "width": 8, "precision": 2},
    {"label": "PriceClose", "key": "tradePriceClose", "width": 9, "precision": 2},
    {"label": "NetCashCl", "key": "netCashClose", "width": 9, "precision": 2},
    # {"label": "Strategy", "key": "strategy", "width": 8},
    {"label": "Profit", "key": "profit", "width": 9, "precision": 2},
    {"label": "Status", "key": "status", "width": 10},
]


class ClosedTradeSchema(BaseSchema):
    FIELDS = [
        'symID',
        'assetCategory',
        'subCategory',
        'symbol',
        'description',
        'underlyingSymbol',
        'underlyingConid',
        'conid',
        'dateTimeOpen',
        'dateTimeClose',
        'putCall',
        'buySellOpen',
        'buySellClose',
        'quantity',
        'tradePriceOpen',
        'tradePriceClose',
        'netCashOpen',
        'netCashClose',
        'proceedsOpen',
        'proceedsClose',
        'daysHeld',
        'totalSeconds',
        'durationStr',
        'profit',
        'ROI',
        'strategy',
        'status',
        'tradeIDOpen',
        'tradeIDClose',
        'ibOrderIDOpen',
        'ibOrderIDClose',
        'ibCommission',
        'currency',
        'fxRateToBase_open',
        'fxRateToBase_close',
        'netCashOpen_EUR',
        'netCashClose_EUR',
        'ibCommission_EUR',
        'profit_EUR',
        'closedBy', # z.B.SELL / EXPIRY / ASSIGNMENT
        'linkID',
        'opt_strategy',
        'opt_strategyName',
        'opt_strategyID',
        'environment',
    ]

    REQUIRED_FIELDS = [
        'symbol',
        'quantity',
        'tradePriceOpen',
        'tradePriceClose',
        'dateTimeOpen',
        'dateTimeClose',
        'tradeID'
    ]

    FIELD_MAPPINGS = {
        # 'assetClass': 'assetCategory',
    }

    TABLE_NAME = TABLE_TRADES_CLOSE

    @classmethod
    def validate(cls, data: Dict[str, Any]) -> List[str]:
        errors = super().validate(data)
        # Additional validations specific to closed trades
        if 'status' in data and not data['status'] in ['Closed', 'Expired', 'CashSettled', 'Assigned', 'Unknown']:
            errors.append("Status must be 'Closed' or 'Expired' for closed trades")
            print(data)

        if 'dateTimeOpen' in data and 'dateTimeClose' in data:
            try:
                # Hilfsfunktion zur internen Umwandlung (nur für den Vergleich)
                def ensure_datetime(val):
                    if isinstance(val, datetime):
                        return val
                    if isinstance(val, date):  # Falls es nur ein date-Objekt ist
                        return datetime.combine(val, datetime.min.time())
                    # Falls es doch noch ein String ist, parsen:
                    return datetime.strptime(val, '%Y-%m-%d')

                open_date = ensure_datetime(data['dateTimeOpen'])
                close_date = ensure_datetime(data['dateTimeClose'])

                if close_date < open_date:
                    errors.append("Close date cannot be before open date")

            except (ValueError, TypeError):
                errors.append("Invalid date format for dateTimeOpen or dateTimeClose")

        return errors

    @classmethod
    def log_closed_trade(cls, closed_trade, prefix: str = "Cl", partial: bool = False):
        # Normalisiere die Daten vor dem Logging
        closed_trade = cls.normalize_date_fields(closed_trade)

        if partial:
            sym = BOX_HEAVY_VERTICAL_AND_RIGHT
        else:
            sym = BOX_HEAVY_UP_AND_RIGHT

        if closed_trade['assetCategory'] == 'OPT':
            prefix = f"{prefix} OPT"
            print_log(logger, format_header(close_columns_opt, border=BOX_HEAVY_VERTICAL, prefix=prefix), True)
            print_log(logger, format_row(closed_trade, close_columns_opt, border=sym), True)
        else:
            prefix = f"{prefix} STK"
            print_log(logger, format_header(close_columns, border=BOX_HEAVY_VERTICAL, prefix=prefix), True)
            print_log(logger, format_row(closed_trade, close_columns, border=sym), True)
