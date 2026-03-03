# corporate_utils.py
# Daten für die verschiedenen Splits nur an einer Stelle

SPLIT_TYPES = {"RS",  # "REVERSE_SPLIT"
               "SS",  # "STOCK_SPLIT"
               "FS"  # "FORWARD_SPLIT"
               }


def get_split_info(trade_type):
    """Gibt den Typ zurück, wenn es ein Split ist, sonst None."""
    return trade_type if trade_type in SPLIT_TYPES else None
