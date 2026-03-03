from typing import Dict, Any, List
from datetime import datetime
from .base_schema import BaseSchema
from src.logger_setup import setup_logging, fmt


class PositionSchema(BaseSchema):
    FIELDS = [
        'gid',
        'assetCategory',
        'symbol',
        'quantity',
        'averagePrice',
        'marketPrice',
        'marketValue',
        'unrealizedPnL',
        'updateTime'
    ]

    REQUIRED_FIELDS = [
        'symbol',
        'quantity',
        'averagePrice'
    ]

    FIELD_MAPPINGS = {
        'assetClass': 'assetCategory',
    }

    TABLE_NAME = 'positions'

    @classmethod
    def validate(cls, data: Dict[str, Any]) -> List[str]:
        """Extended validation for positions"""
        errors = super().validate(data)

        # Additional validations
        if 'quantity' in data and data['quantity'] == 0:
            errors.append("Position quantity cannot be zero")

        return errors

    @classmethod
    def from_open_trade(cls, open_trade: Dict[str, Any]) -> Dict[str, Any]:
        """Create a position from an open trade"""
        position = cls.create_empty_dict()

        # Map relevant fields
        position['symbol'] = open_trade.get('symbol')
        position['assetCategory'] = open_trade.get('assetCategory')
        # Set price information
        position['averagePrice'] = open_trade.get('tradePrice')
        position['marketPrice'] = open_trade.get('tradePrice')  # Initially same as purchase price

        # Handle quantity based on buy/sell
        quantity = open_trade.get('quantity', 0)
        if open_trade.get('buySell') == 'SELL':
            quantity = -quantity
        position['quantity'] = quantity

        # Calculate market value
        price = open_trade.get('tradePrice', 0)
        multiplier = open_trade.get('multiplier', 1)
        position['marketValue'] = price * abs(quantity) * multiplier

        # Set update time to now
        position['updateTime'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        return position
