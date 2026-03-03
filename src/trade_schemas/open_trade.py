# trade_schemas/open_trade.py
import pandas as pd
from typing import Dict, Any, List
from datetime import datetime
from .base_schema import BaseSchema
from .closed_trade import ClosedTradeSchema
from src.logger_setup import setup_logging, format_header, format_row, print_log
from src.utils.path_utils import get_project_root
from src.utils.div_utils import to_decimal, calculate_hold_metrics
from src.config import TABLE_TRADES_OPEN

BOX_HEAVY_VERTICAL = '\u2503'  # ┃
BOX_HEAVY_UP_AND_RIGHT = '\u2517'  # ┗
BOX_HEAVY_VERTICAL_AND_RIGHT = '\u2523'  # ┣

# Get logger - use the same logger name across all files
log_file = get_project_root() / "log/app.log"
logger, _ = setup_logging('my_app', level="simple", log_file=log_file)

open_columns = [
    {"label": "id", "key": "tradeID", "width": 12},
    {"label": "Symbol", "key": "symbol", "width": 6},
    {"label": "DateOpen", "key": "dateTime", "width": 17},
    {"label": "B/S", "key": "buySell", "width": 4},
    {"label": "Quantity", "key": "quantity", "width": 8, "precision": 2},
    {"label": "Price", "key": "tradePrice", "width": 9, "precision": 2},
    {"label": "NetCash", "key": "netCash", "width": 9, "precision": 2},
    {"label": "Strategy", "key": "strategy", "width": 8},
]
open_columns_opt = [
    {"label": "id", "key": "tradeID", "width": 12},
    {"label": "Symbol", "key": "description", "width": 19},
    {"label": "DateOpen", "key": "dateTime", "width": 17},
    {"label": "B/S", "key": "buySell", "width": 4},
    {"label": "Quantity", "key": "quantity", "width": 8, "precision": 2},
    {"label": "Price", "key": "tradePrice", "width": 9, "precision": 2},
    {"label": "NetCash", "key": "netCash", "width": 9, "precision": 2},
    {"label": "Strategy", "key": "strategy", "width": 8},
]
open_columns_upd = [
    {"label": "id", "key": "tradeID", "width": 12},
    {"label": "Symbol", "key": "symbol", "width": 6},
    {"label": "DateOpen", "key": "dateTime", "width": 17},
    {"label": "B/S", "key": "buySell", "width": 4},
    {"label": "QuantNew", "key": "quantity", "width": 8, "precision": 2},
    {"label": "Price", "key": "tradePrice", "width": 9, "precision": 6},
    {"label": "NetCash", "key": "netCash", "width": 9, "precision": 2},
    {"label": "Strategy", "key": "strategy", "width": 8},
]
open_columns_opt_upd = [
    {"label": "id", "key": "tradeID", "width": 12},
    {"label": "Symbol", "key": "description", "width": 19},
    {"label": "DateOpen", "key": "dateTime", "width": 17},
    {"label": "B/S", "key": "buySell", "width": 4},
    {"label": "QuantNew", "key": "quantity", "width": 8, "precision": 2},
    {"label": "Price", "key": "tradePrice", "width": 9, "precision": 2},
    {"label": "NetCash", "key": "netCash", "width": 9, "precision": 2},
    {"label": "Strategy", "key": "strategy", "width": 8},
]


class OpenTradeSchema(BaseSchema):
    # Define fields specific to the open trades table
    FIELDS = [
        'symID',
        'assetCategory',
        'subCategory',
        'symbol',
        'description',
        'underlyingSymbol',
        'underlyingConid',
        'conid',
        'quantity',
        'expiry',
        'buySell',
        'putCall',
        'strike',
        'multiplier',
        'dateTime',
        'tradePrice',
        'netCash',
        'proceeds',
        'ibCommission',
        'currency',
        'fxRateToBase',
        'fifoPnlRealized',
        'strategy',
        'status',
        'tradeID',
        'ibOrderID',
        'linkID',
        'opt_strategy',
        'opt_strategyName',
        'opt_strategyID',
        'environment',
        'checksum',
        'processed'
    ]

    REQUIRED_FIELDS = [
        'symbol',
        'quantity',
        'tradePrice',
        'dateTime',
    ]

    FIELD_MAPPINGS = {
        # 'assetClass': 'assetCategory',
        # 'price': 'tradePrice'
    }

    TABLE_NAME = TABLE_TRADES_OPEN

    @classmethod
    def validate(cls, data: Dict[str, Any]) -> List[str]:
        """Extended validation for open trades"""
        errors = super().validate(data)

        # Additional validations specific to open trades
        # für das Einfügen eines Dummy-Trades muss ich das auskommentieren (weil die quantity = 0)
        # if 'quantity' in data and data['quantity'] is not None:
        #     if data['quantity'] == 0:
        #         errors.append("Quantity cannot be zero for an open trade")

        OPEN_STATUSES = {'OPEN', 'REV_OPEN', 'SPLIT_REST'}
        if 'status' in data:
            if str(data['status']).upper() not in OPEN_STATUSES:
                errors.append("Invalid status for open trade")
        return errors

    @classmethod
    def to_closed_trade(cls, open_trade: Dict[str, Any], close_data: Dict[str, Any], ratio) -> Dict[str, Any]:
        """Convert an open trade to a closed trade"""
        open_trade = cls.normalize_date_fields(open_trade)
        close_data = cls.normalize_date_fields(close_data)

        closed_trade = ClosedTradeSchema.create_empty_dict()
        close_portion = to_decimal(ratio)

        # Map common fields that have the same name
        for field in ['symID', 'assetCategory', 'symbol', 'description', 'underlyingSymbol', 'underlyingConid',
                      'putCall', 'strategy', 'tradeID', 'subCategory', 'quantity', 'environment','fifoPnlRealized',
                      'linkID', 'opt_strategy', 'opt_strategyName', 'opt_strategyID', 'closedBy', 'conid']:
            if field in open_trade:
                closed_trade[field] = open_trade.get(field)

        # Map fields with different names
        closed_trade['dateTimeOpen'] = open_trade.get('dateTime')
        closed_trade['buySellOpen'] = open_trade.get('buySell')
        closed_trade['quantity'] = open_trade.get('quantity')
        closed_trade['tradePriceOpen'] = open_trade.get('tradePrice')
        closed_trade['netCashOpen'] = open_trade.get('netCash')
        closed_trade['proceedsOpen'] = open_trade.get('proceeds')
        closed_trade['tradeIDOpen'] = open_trade.get('tradeID')
        closed_trade['ibOrderIDOpen'] = open_trade.get('ibOrderID')

        # Set closing fields from close_data
        closed_trade['dateTimeClose'] = close_data.get('dateTime')
        closed_trade['buySellClose'] = close_data.get('buySell')
        closed_trade['tradePriceClose'] = close_data.get('tradePrice')

        net_cash_close = close_data.get('netCash') * close_portion
        closed_trade['netCashClose'] = net_cash_close

        closed_trade['proceedsClose'] = close_data.get('proceeds') * close_portion
        closed_trade['tradeIDClose'] = close_data.get('tradeID')
        closed_trade['ibOrderIDClose'] = close_data.get('ibOrderID')

        # Calculate days held
        open_dt = open_trade.get('dateTime')
        close_dt = close_data.get('dateTime')

        days_held, total_seconds, duration_text = calculate_hold_metrics(open_dt, close_dt)
        closed_trade['daysHeld'] = days_held
        closed_trade['totalSeconds'] = total_seconds
        closed_trade['durationStr'] = duration_text

        open_commission = to_decimal(open_trade.get('ibCommission', 0) or 0) * close_portion
        close_commission = to_decimal(close_data.get('ibCommission', 0) or 0)
        closed_trade['ibCommission'] = to_decimal(open_commission + close_commission)

        # EUR-Werte: FX-Kurse zum jeweiligen Handelszeitpunkt
        fxRate_open  = to_decimal(open_trade.get('fxRateToBase') or 1)
        fxRate_close = to_decimal(close_data.get('fxRateToBase') or 1)

        closed_trade['currency']           = open_trade.get('currency')
        closed_trade['fxRateToBase_open']  = fxRate_open
        closed_trade['fxRateToBase_close'] = fxRate_close

        closed_trade['netCashOpen_EUR']  = to_decimal(closed_trade['netCashOpen'])  * fxRate_open
        closed_trade['netCashClose_EUR'] = to_decimal(closed_trade['netCashClose']) * fxRate_close

        # Kommission: Open-Anteil mit Open-Kurs, Close-Anteil mit Close-Kurs
        closed_trade['ibCommission_EUR'] = to_decimal(open_commission * fxRate_open + close_commission * fxRate_close)

        closed_trade['profit_EUR'] = closed_trade['netCashOpen_EUR'] + closed_trade['netCashClose_EUR']

        def calculate_roi(cost_of_investment, net_profit):
            if cost_of_investment == 0:
                return 100
            roi = abs((net_profit / cost_of_investment) * 100)
            if net_profit < 0:
                roi = -roi
            return roi

        # profit = to_decimal(net_cash_close + open_trade.get('netCash'))
        profit_open = to_decimal(open_trade.get('fifoPnlRealized'))
        profit_close = to_decimal(close_data.get('fifoPnlRealized')) * close_portion
        print(f"Open Pnl: {profit_open}, Close Pnl: {profit_close}")
        profit = profit_open + profit_close
        closed_trade['profit'] = to_decimal(profit)
        closed_trade['ROI'] = to_decimal(calculate_roi(closed_trade['netCashOpen'], profit))

        # Set status
        status =  close_data.get('status', 'Closed')
        if pd.isna(status) or status in ('', None):
            status = 'Closed'
        closed_trade['status'] = status

        return closed_trade

    @classmethod
    def partial_close_new_open(cls, open_trade: Dict[str, Any], close_data: Dict[str, Any],
                               closing_proportion) -> Dict[str, Any]:
        # Case 2a: Open trade larger - partial close, update open trade
        # close_data wird geschlossen
        # open_trade wird um close_data reduziert und neu erstellt

        """Convert an open trade to a closed trade"""
        open_trade = cls.normalize_date_fields(open_trade)
        close_data = cls.normalize_date_fields(close_data)

        closed_trade = ClosedTradeSchema.create_empty_dict()
        close_portion = to_decimal(closing_proportion)

        # Map common fields that have the same name
        for field in ['symID', 'assetCategory', 'symbol', 'description', 'underlyingSymbol', 'underlyingConid',
                      'putCall', 'strategy', 'tradeID', 'subCategory', 'quantity', 'environment', 'fifoPnlRealized',
                      'linkID', 'opt_strategy', 'opt_strategyName', 'opt_strategyID', 'conid']:
            if field in open_trade:
                closed_trade[field] = open_trade.get(field)

        # Map fields with different names
        closed_trade['dateTimeOpen'] = open_trade.get('dateTime')
        closed_trade['buySellOpen'] = open_trade.get('buySell')
        closed_trade['quantity'] = close_data.get('quantity')  # für den Closeteil diesmal aus den clse_data
        closed_trade['tradePriceOpen'] = open_trade.get('tradePrice')
        net_cash_open = open_trade.get('netCash') * close_portion
        closed_trade['netCashOpen'] = net_cash_open
        closed_trade['proceedsOpen'] = open_trade.get('proceeds') * close_portion
        closed_trade['tradeIDOpen'] = open_trade.get('tradeID')
        closed_trade['ibOrderIDOpen'] = open_trade.get('ibOrderID')

        # Set closing fields from close_data
        closed_trade['dateTimeClose'] = close_data.get('dateTime')
        closed_trade['buySellClose'] = close_data.get('buySell')
        closed_trade['tradePriceClose'] = close_data.get('tradePrice')

        closed_trade['netCashClose'] = close_data.get('netCash')

        closed_trade['proceedsClose'] = close_data.get('proceeds')
        closed_trade['tradeIDClose'] = close_data.get('tradeID')
        closed_trade['ibOrderIDClose'] = close_data.get('ibOrderID')

        # Calculate days held
        open_dt = open_trade.get('dateTime')
        close_dt = close_data.get('dateTime')

        days_held, total_seconds, duration_text = calculate_hold_metrics(open_dt, close_dt)
        closed_trade['daysHeld'] = days_held
        closed_trade['totalSeconds'] = total_seconds
        closed_trade['durationStr'] = duration_text

        # Sum commissions from open and close
        open_commission = to_decimal(open_trade.get('ibCommission', 0) or 0) * close_portion
        close_commission = to_decimal(close_data.get('ibCommission', 0) or 0)
        closed_trade['ibCommission'] = to_decimal(open_commission + close_commission)

        def calculate_roi(cost_of_investment, net_profit):
            if cost_of_investment == 0:
                return 100
            roi = abs((net_profit / cost_of_investment) * 100)
            if net_profit < 0:
                roi = -roi
            return roi

        # profit = to_decimal(net_cash_open + close_data.get('netCash'))
        profit_open = to_decimal(open_trade.get('fifoPnlRealized'))
        profit_close = to_decimal(close_data.get('fifoPnlRealized'))
        print(f"Open Pnl: {profit_open}, Close Pnl: {profit_close}")
        profit = profit_open + profit_close
        closed_trade['profit'] = to_decimal(profit)
        closed_trade['ROI'] = to_decimal(calculate_roi(net_cash_open, profit))

        # Set status
        closed_trade['status'] = close_data.get('status', 'Closed')
        if closed_trade['status'] in (None, ''):
            closed_trade['status'] = 'Closed'

        return closed_trade

    @classmethod
    def to_update_trade(cls, open_trade: Dict[str, Any], new_trade: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing open trade by averaging with a new trade of the same direction
        Used when adding to a position
        """
        updated_trade = open_trade.copy()

        # Calculate new total quantity
        old_qty = open_trade.get('quantity', 0) or 0
        new_qty = new_trade.get('quantity', 0) or 0
        total_qty = old_qty + new_qty

        if total_qty == 0:
            return updated_trade  # Avoid division by zero

        # Calculate weighted average price
        old_price = open_trade.get('tradePrice', 0) or 0
        new_price = new_trade.get('tradePrice', 0) or 0
        avg_price = ((old_price * old_qty) + (new_price * new_qty)) / total_qty

        # Update the values
        updated_trade['quantity'] = total_qty
        updated_trade['tradePrice'] = round(avg_price, 4)

        # Sum the cash values
        updated_trade['netCash'] = (open_trade.get('netCash', 0) or 0) + (new_trade.get('netCash', 0) or 0)
        updated_trade['proceeds'] = (open_trade.get('proceeds', 0) or 0) + (new_trade.get('proceeds', 0) or 0)
        updated_trade['ibCommission'] = (open_trade.get('ibCommission', 0) or 0) + (
                new_trade.get('ibCommission', 0) or 0)

        # Use the latest trade date/time
        if new_trade.get('dateTime'):
            try:
                old_date = datetime.strptime(open_trade.get('dateTime', '1900-01-01'), '%Y-%m-%d')
                new_date = datetime.strptime(new_trade.get('dateTime', '1900-01-01'), '%Y-%m-%d')

                if new_date > old_date:
                    updated_trade['dateTime'] = new_trade.get('dateTime')
            except (ValueError, TypeError):
                # Keep the old date if there's an error
                pass

        return updated_trade

    @classmethod
    def to_update_split_trade(cls, open_trade: Dict[str, Any], new_trade: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing open trade after a split -> the factor is in 'multiplier'
        calculate new quantiy and price
        """
        updated_trade = open_trade.copy()

        factor = new_trade.get('multiplier', 0) or 0
        if factor == 0:
            return updated_trade  # Avoid division by zero

        # Calculate new total quantity
        old_qty = open_trade.get('quantity', 0) or 0
        new_qty = old_qty * factor

        # Calculate weighted average price
        old_price = open_trade.get('tradePrice', 0) or 0
        new_price = old_price / factor

        # Update the values
        updated_trade['quantity'] = new_qty
        updated_trade['tradePrice'] = round(new_price, 4)

        # Use the latest trade date/time
        if new_trade.get('dateTime'):
            try:
                old_date = datetime.strptime(open_trade.get('dateTime', '1900-01-01'), '%Y-%m-%d')
                new_date = datetime.strptime(new_trade.get('dateTime', '1900-01-01'), '%Y-%m-%d')

                if new_date > old_date:
                    updated_trade['dateTime'] = new_trade.get('dateTime')
            except (ValueError, TypeError):
                # Keep the old date if there's an error
                pass

        return updated_trade

    # @classmethod
    # def handle_trades(cls, open_trade: Dict[str, Any], new_trade: Dict[str, Any]) -> tuple:
    #     """
    #     Handle trade processing based on trade directions
    #     Returns (action, result) where:
    #     - action is 'update', 'close', or 'close_new'
    #     - result is the relevant trade data
    #     """
    #     # Normalisiere Datums- und Zeitfelder
    #     open_trade = cls.normalize_date_fields(open_trade)
    #     new_trade = cls.normalize_date_fields(new_trade)
    #
    #     # # Handle Split - Trades
    #     # # if new_trade['source'] == 'split' and new_trade['is_split'] == 1 and new_trade['split_type'] in ("RS", "SS", "FS"):
    #     # # Wenn split_type schon "RS", "SS" oder "FS" ist,
    #     # # muss es nicht nochmal gegen die Liste geprüft werden.
    #     # if new_trade['source'] == 'split' and new_trade['split_type']:
    #     #     # found
    #     #     updated_trade = cls.to_update_split_trade(open_trade, new_trade)
    #     #     return 'update_split', updated_trade
    #
    #     open_sign = math.copysign(1, open_trade['quantity'])
    #     new_sign = math.copysign(1, new_trade['quantity'])
    #
    #     # Case 1: Same sign - combine positions
    #     if open_sign == new_sign:
    #         updated_trade = cls.to_update_trade(open_trade, new_trade)
    #         return 'update', updated_trade
    #
    #     # Case 2: Different signs - various closing scenarios
    #     total_quantity = open_trade['quantity'] + new_trade['quantity']
    #
    #     # Case 2c: Quantities sum to zero - full close
    #     if abs(total_quantity) < 0.0001:
    #         closed_trade = cls.to_closed_trade(open_trade, new_trade)
    #         return 'close', closed_trade
    #
    #     # Determine which trade is larger
    #     open_abs = abs(open_trade['quantity'])
    #     new_abs = abs(new_trade['quantity'])
    #
    #     if open_abs > new_abs:
    #         # Case 2a: Open trade larger - partial close, update open trade
    #
    #         # Erstelle eine angepasste Kopie des open_trade für to_closed_trade
    #         open_trade_adjusted = open_trade.copy()
    #
    #         # Proportionale Anpassung der Werte für den zu schließenden Teil
    #         closing_proportion = new_abs / open_abs
    #         open_trade_adjusted['quantity'] = open_trade['quantity'] * closing_proportion
    #         open_trade_adjusted['netCash'] = open_trade.get('netCash', 0) * closing_proportion
    #         open_trade_adjusted['proceeds'] = open_trade.get('proceeds', 0) * closing_proportion
    #         open_trade_adjusted['ibCommission'] = open_trade.get('ibCommission', 0) * closing_proportion
    #
    #         # Create closed trade record für diesen angepassten Teil
    #         closed_trade = cls.to_closed_trade(open_trade_adjusted, new_trade)
    #
    #         # Update open trade mit der verbleibenden Menge
    #         updated_open = open_trade.copy()
    #         updated_open['quantity'] = total_quantity
    #
    #         # Anpassung der finanziellen Werte für den verbleibenden Teil
    #         remaining_proportion = Decimal('1.0') - closing_proportion
    #         updated_open['netCash'] = open_trade.get('netCash', 0) * remaining_proportion
    #         updated_open['proceeds'] = open_trade.get('proceeds', 0) * remaining_proportion
    #         updated_open['ibCommission'] = open_trade.get('ibCommission', 0) * remaining_proportion
    #
    #         return 'close_update', (closed_trade, updated_open)
    #     else:
    #         # Case 2b: New trade larger - close open trade, create new trade
    #
    #         # Erstelle eine angepasste Kopie des new_trade für to_closed_trade
    #         new_trade_adjusted = new_trade.copy()
    #
    #         # Proportionale Anpassung der Werte für den zu schließenden Teil
    #         closing_proportion = open_abs / new_abs
    #         new_trade_adjusted['quantity'] = new_trade['quantity'] * closing_proportion
    #         new_trade_adjusted['netCash'] = new_trade.get('netCash', 0) * closing_proportion
    #         new_trade_adjusted['ibCommission'] = new_trade.get('ibCommission', 0) * closing_proportion
    #
    #         # Create closed trade record für den vollen open_trade
    #         closed_trade = cls.to_closed_trade(open_trade, new_trade_adjusted)
    #
    #         # Create new open trade mit der verbleibenden Menge
    #         new_open = new_trade.copy()
    #         new_open['quantity'] = total_quantity
    #         new_open['status'] = 'Open'
    #
    #         # Anpassung der finanziellen Werte für den verbleibenden Teil
    #         remaining_proportion = 1.0 - closing_proportion
    #         new_open['netCash'] = new_trade.get('netCash', 0) * remaining_proportion
    #         new_open['ibCommission'] = new_trade.get('ibCommission', 0) * remaining_proportion
    #
    #         return 'close_new', (closed_trade, new_open)

    @classmethod
    def log_open_trade(cls, open_trade, prefix: str = "Op", flag: bool = False):
        # Normalisiere die Daten vor dem Logging
        open_trade = cls.normalize_date_fields(open_trade)
        op_cols = open_columns
        op_cols_opt = open_columns_opt
        if flag:
            op_cols = open_columns_upd
            op_cols_opt = open_columns_opt_upd

        sym = BOX_HEAVY_UP_AND_RIGHT

        if open_trade['assetCategory'] == 'OPT':
            prefix = f"{prefix} OPT"
            print_log(logger, format_header(op_cols_opt, border=BOX_HEAVY_VERTICAL, prefix=prefix), True)
            print_log(logger, format_row(open_trade, op_cols_opt, border=sym), True)
        else:
            prefix = f"{prefix} STK"
            print_log(logger, format_header(op_cols, border=BOX_HEAVY_VERTICAL, prefix=prefix), True)
            print_log(logger, format_row(open_trade, op_cols, border=sym), True)
