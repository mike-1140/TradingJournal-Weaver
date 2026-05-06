# trade_schemas/base_schema.py

import pandas as pd
from datetime import datetime, date, timedelta
from typing import List, Dict, Any
from src.utils.div_utils import parse_datetime_flex

# imports, um darüberliegende zufriedenzustellen !!!
# from .open_trade import OpenTradeSchema
# from .closed_trade import ClosedTradeSchema


class ValidationError(Exception):
    """Custom exception for validation errors"""
    pass


class BaseSchema:
    """Base schema class with common functionality"""
    FIELDS: List[str] = []
    REQUIRED_FIELDS: List[str] = []
    FIELD_MAPPINGS: Dict[str, str] = {}
    TABLE_NAME: str = ""

    @classmethod
    def create_empty_dict(cls) -> Dict[str, Any]:
        """Create an empty dictionary with all fields set to None"""
        return {field: None for field in cls.FIELDS}

    @classmethod
    def map_field_name(cls, field_name: str) -> str:
        """Map field names if they differ between systems"""
        return cls.FIELD_MAPPINGS.get(field_name, field_name)

    @classmethod
    def get_db_field_names(cls) -> List[str]:
        """Get field names for database operations"""
        return [cls.map_field_name(field) for field in cls.FIELDS]

    @classmethod
    def get_db_placeholders(cls) -> str:
        return ', '.join([f":{field}" for field in cls.FIELDS])

    # @classmethod
    # def get_db_placeholders(cls) -> str:
    #     """Generate SQL placeholders for prepared statements"""
    #     return ', '.join(['%s'] * len(cls.FIELDS))

    @classmethod
    def validate(cls, data: Dict[str, Any]) -> List[str]:
        """
        Validate the data against the schema requirements
        Returns a list of validation error messages (empty if valid)
        """
        errors = []
        # Check for missing required fields
        for field in cls.REQUIRED_FIELDS:
            val = data.get(field)
            if val is None or (isinstance(val, float) and pd.isna(val)):
                errors.append(f"Missing required field: {field}")

        # Check for unexpected fields (not defined in schema)
        # extra_fields = set(data.keys()) - set(cls.FIELDS)
        # for field in extra_fields:
        #     errors.append(f"Unexpected field: {field}")
        return errors

    @classmethod
    def validate_and_raise(cls, data: Dict[str, Any]) -> None:
        """Validate data and raise exception if invalid"""
        errors = cls.validate(data)
        if errors:
            raise ValidationError('\n'.join(errors))

    @classmethod
    def normalize_date_fields(cls, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Stellt sicher, dass Datumsfelder echte datetime-Objekte sind.
        Schneidet keine Uhrzeiten mehr ab!
        """
        if trade_data is None:
            return {}

        normalized = trade_data.copy()
        # Alle Felder, die Zeitinformationen enthalten können
        date_fields = ['dateTime', 'dateTimeOpen', 'dateTimeClose', 'expiry']

        for field in date_fields:
            if field in normalized and normalized[field] is not None:
                value = normalized[field]

                # Falls es ein reines 'date' ist, zu 'datetime' (Mitternacht) machen
                if isinstance(value, date) and not isinstance(value, datetime):
                    normalized[field] = datetime.combine(value, datetime.min.time())

                # Falls es bereits ein datetime ist: Einfach so lassen!
                # Falls es ein String ist (z.B. aus CSV oder IBKR), hier parsen:
                elif isinstance(value, str):
                    parsed = parse_datetime_flex(value)
                    if parsed is not None:
                        normalized[field] = parsed

        return normalized
