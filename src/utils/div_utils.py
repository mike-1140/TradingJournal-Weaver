# src/utils/div_utils.py

import hashlib
import pandas as pd
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta


def to_decimal(val):
    """Wandelt Eingaben sicher in Decimal um, statt in Float."""
    if val is None or val == "":
        return Decimal('0.0000')

    # Wenn bereits eine Zahl (int, float, Decimal)
    if isinstance(val, (int, float, Decimal)):
        # Wichtig: float immer erst über String in Decimal wandeln!
        return Decimal(str(val))

    try:
        # Hier ist es ein String
        val = str(val).strip()
        val = val.replace("+", "")

        # Tausender-Trennzeichen Logik
        if "," in val and "." in val:
            # Annahme: 1,000.50 -> Komma weg
            val = val.replace(",", "")
        elif "," in val and "." not in val:
            # Annahme: 1000,50 (EU-Format) -> Komma zu Punkt
            val = val.replace(",", ".")

        return Decimal(val)
    except (InvalidOperation, ValueError):
        return Decimal('0.0000')


def compute_checksum(trade):
    # Prüfen, ob es sich vermutlich um einen FX-Trade handelt
    fx_flag = 'baseAmount' in trade and 'quoteAmount' in trade

    if fx_flag:
        checksum_fields = ['tradeID', 'dateTime', 'symbol', 'baseAmount', 'quoteAmount']
    else:
        checksum_fields = ['tradeID', 'dateTime', 'symbol', 'quantity', 'tradePrice']

    # Nur Felder einbeziehen, die tatsächlich existieren (z. B. falls Daten unvollständig sind)
    available_fields = [f for f in checksum_fields if f in trade and pd.notna(trade[f])]

    # Checksum-String bilden
    checksum_str = '|'.join(str(trade.get(field, '')) for field in available_fields)

    # MD5 berechnen (auf 12 Zeichen gekürzt)
    return hashlib.md5(checksum_str.encode("utf-8")).hexdigest()[:12]


def parse_datetime_flex(dt_raw, logger=None):
    if not dt_raw or pd.isna(dt_raw):
        return None

    # Bekannte IBKR-Formate
    # 1. "23/09/2025;102924" (Standard Flex Query)
    # 2. "2025-09-23" (Nur Datum)
    # 3. "10:29:24" (Nur Zeit - heute)

    try:
        # Versuch 1: IBKR-Format mit Semikolon (Paper: DD/MM/YYYY;HHMMSS, Echtgeld: YYYYMMDD;HHMMSS)
        if ';' in str(dt_raw):
            try:
                return pd.to_datetime(dt_raw, format="%d/%m/%Y;%H%M%S")
            except ValueError:
                return pd.to_datetime(dt_raw, format="%Y%m%d;%H%M%S")

        # Versuch 2: YYYYMMDD ohne Trennzeichen (IBKR-Format)
        s = str(dt_raw).strip()
        if s.isdigit() and len(s) == 8:
            return pd.to_datetime(s, format="%Y%m%d")

        # Versuch 3: Flexibler Parser für den Rest (ISO, DD-MM-YYYY etc.)
        # dayfirst=True ist wichtig für europäischen Kontext
        return pd.to_datetime(dt_raw, dayfirst=True)

    except Exception as e:
        # Letzter Rettungsanker: Falls es ein reiner Zeit-String ist
        try:
            if ':' in str(dt_raw) and len(str(dt_raw)) <= 8:
                # Ergänze heutiges Datum für Zeit-Only Strings
                return pd.to_datetime(dt_raw).replace(
                    year=pd.Timestamp.now().year,
                    month=pd.Timestamp.now().month,
                    day=pd.Timestamp.now().day
                )
        except:
            pass

        if logger:
            logger.warning(f"Konnte Datum nicht parsen: {dt_raw} | Fehler: {e}")
        return None


def calculate_hold_metrics(open_dt: datetime, close_dt: datetime):
    """
    Berechnet alle zeitrelevanten Metriken für einen geschlossenen Trade.
    """
    if not (isinstance(open_dt, datetime) and isinstance(close_dt, datetime)):
        return 0, 0, "N/A"

    diff = close_dt - open_dt
    total_seconds = int(diff.total_seconds())

    # 1. Tage als reine Zahl (für Statistik)
    days_held = diff.days

    # 2. Lesbarer String (Stunden/Minuten)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, _ = divmod(remainder, 60)

    if hours < 24:
        duration_str = f"{hours}h {minutes}m"
    else:
        d, h = divmod(hours, 24)
        duration_str = f"{d}d {h}h"

    return days_held, total_seconds, duration_str

