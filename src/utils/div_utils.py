# src/utils/div_utils.py

import hashlib
import pandas as pd
import numpy as np
from typing import Union, List, Dict, Any
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


def watch_fields(df, stage_name="unbekannt", fields=None, id_field="tradeID", verbose=False):
    """
    Überwacht wichtige Felder im DataFrame und meldet fehlende (NaN/None) Werte.
    - df: Pandas DataFrame
    - stage_name: Name des Verarbeitungsabschnitts (z.B. 'nach detect_strategies')
    - fields: Liste der zu überprüfenden Spalten
    - id_field: optionales Feld zur Identifikation betroffener Zeilen
    - verbose: True = zeigt Beispielzeilen
    """
    if fields is None:
        fields = ["opt_strategy", "strategy_name", "strategy_lnk"]

    print(f"\n🔍 [Watch] Überprüfung nach Schritt: '{stage_name}'")
    total = len(df)
    issues_found = False

    for field in fields:
        if field not in df.columns:
            print(f"⚠️  Feld '{field}' fehlt im DataFrame!")
            continue

        missing = df[field].isna().sum()
        if missing > 0:
            issues_found = True
            print(f"❌  {missing}/{total} Zeilen mit fehlendem '{field}'")
            if verbose:
                cols_to_show = [id_field, field] if id_field in df.columns else [field]
                cols_to_show += [c for c in ["transactionType", "source", "underlyingSymbol", "expiry"] if
                                 c in df.columns]
                print(df.loc[df[field].isna(), cols_to_show].head(10))
        else:
            print(f"✅  '{field}' vollständig initialisiert.")

    if not issues_found:
        print("🎯  Alle überwachten Felder sind sauber.")


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


def print_selected(data, text, fields):
    """
    Gibt Felder aus einem DataFrame oder Dict aus.
    Strikte Begrenzung auf 15 Zeichen pro Spalte.
    """
    # 1. Daten normalisieren
    if isinstance(data, pd.DataFrame):
        items = data.to_dict(orient='records')
        available = data.columns.tolist()
    elif isinstance(data, dict):
        items = [data]
        available = list(data.keys())
    elif isinstance(data, list):
        items = data
        available = list(set().union(*(d.keys() for d in items)))
    else:
        return

    # 2. Felder filtern
    fields = [f for f in fields if f in available]
    if not fields:
        print(f"{text} Keine passenden Felder gefunden.")
        return

    # 3. Kopfzeile (auch hier strikt 15 Zeichen)
    print(f"\n{text}")
    header = " | ".join(f"{str(f)[:15]:<15}" for f in fields)
    print(header)
    print("-" * len(header))

    # 4. Daten ausgeben
    for row in items:
        line_parts = []
        for col in fields:
            val = row.get(col, "")

            # Formatierung je nach Typ
            if isinstance(val, (int, float, Decimal)) and not isinstance(val, bool):
                # Zahl erst formatieren, dann als String kürzen
                formatted_val = f"{val:.4f}"
                # Rechtsbündig, aber bei Überlänge trotzdem abschneiden
                display_val = formatted_val[:15].rjust(15)
            else:
                # Text/Datum linksbündig und bei über 15 Zeichen abschneiden
                display_val = f"{str(val)[:15]:<15}"

            line_parts.append(display_val)

        print(" | ".join(line_parts))


def smart_print(df, cols=None, max_full=100, head_tail=50):
    """
    Gibt ein DataFrame 'schlau' aus:
    - Wenn <= max_full Zeilen: alle Zeilen + alle Spalten
    - Wenn > max_full Zeilen: zeigt nur head/tail + Gesamtanzahl

    Args:
        df (pd.DataFrame): Das DataFrame
        cols (list): Liste der Spalten (oder None für alle)
        max_full (int): max. Zeilenanzahl, bis alles angezeigt wird
        head_tail (int): wie viele Zeilen oben/unten angezeigt werden, wenn df zu groß
    """
    if cols:
        df = df[cols]

    n_rows = len(df)

    if n_rows <= max_full:
        # alle Zeilen + alle Spalten anzeigen
        with pd.option_context(
                "display.max_rows", None,
                "display.max_columns", None,
                "display.width", None,
                "display.colheader_justify", "left"
        ):
            print(df)
    else:
        # für große DFs: nur head/tail
        with pd.option_context(
                "display.max_columns", None,
                "display.width", None,
                "display.colheader_justify", "left"
        ):
            print(df.head(head_tail))
            print("...\n...\n")
            print(df.tail(head_tail))
            print(f"\n[Gesamtanzahl Zeilen: {n_rows}]")


def diagnose_and_clean(data: Union[pd.DataFrame, List[Dict[str, Any]], Dict[str, Any]]):
    """
    - Ermittelt, ob data ein DataFrame, list[dict] oder dict ist.
    - Druckt Spalten/Keys mit NaN und einige Beispielwerte.
    - Wandelt np.nan in None um und gibt die bereinigte Struktur zurück.
    """

    # Helper: report NaNs in a dataframe
    def report_df(df: pd.DataFrame):
        print("DataFrame shape:", df.shape)
        # Spalten mit NaN
        nan_cols = df.columns[df.isna().any()].tolist()
        if not nan_cols:
            print("Keine NaN-Werte im DataFrame gefunden.")
        else:
            print("Spalten mit NaN:", nan_cols)
            # zeige einige Zeilen mit NaN
            rows_with_nan = df[df.isna().any(axis=1)]
            print("Beispielzeilen mit NaN (bis 10):")
            print(rows_with_nan.head(10))
        # return cleaned df (np.nan -> None)
        cleaned = df.where(pd.notnull(df), None)
        return cleaned

    # Helper: report NaNs in list of dicts
    def report_list_of_dicts(lst: List[Dict[str, Any]]):
        print("List of dicts length:", len(lst))
        # Sammle keys
        all_keys = set()
        for d in lst:
            all_keys.update(d.keys())
        print("Gefundene Keys (Beispiel):", sorted(list(all_keys))[:20])
        # Finde welche keys NaN/np.nan auftauchen
        keys_with_nan = set()
        rows_with_nan = []
        for i, d in enumerate(lst):
            for k, v in d.items():
                # pandas uses np.nan (float) and also pandas.NA etc. handle generically:
                if v is None:
                    continue
                # test for NaN-like
                try:
                    if isinstance(v, float) and np.isnan(v):
                        keys_with_nan.add(k)
                        rows_with_nan.append((i, k, v))
                except Exception:
                    pass
            if len(rows_with_nan) >= 10:
                break
        if not keys_with_nan:
            print("Keine NaN (np.nan) in den dicts gefunden.")
        else:
            print("Keys mit np.nan:", sorted(list(keys_with_nan)))
            print("Einige betroffene Einträge (index, key, value):")
            for item in rows_with_nan[:10]:
                print(item)
        # Clean: replace np.nan with None across all dicts
        cleaned_lst = []
        for d in lst:
            nd = {}
            for k, v in d.items():
                if isinstance(v, float) and np.isnan(v):
                    nd[k] = None
                else:
                    # pandas.NA, pd.NaT check
                    if v is pd.NaT:
                        nd[k] = None
                    else:
                        nd[k] = v
            cleaned_lst.append(nd)
        return cleaned_lst

    # Start
    if isinstance(data, pd.DataFrame):
        cleaned = report_df(data)
        return cleaned

    # list of dicts
    if isinstance(data, list):
        # quick check whether it's list of dicts
        if all(isinstance(x, dict) for x in data):
            cleaned = report_list_of_dicts(data)
            return cleaned
        else:
            raise TypeError("Liste enthält keine dicts. Bitte prüfe die Struktur.")

    # single dict
    if isinstance(data, dict):
        # treat single dict as single-row list
        cleaned_list = report_list_of_dicts([data])
        return cleaned_list[0]

    raise TypeError("Unsupported type. Erwartet DataFrame, list[dict] oder dict.")


# --- Beispielnutzung ---

# 1) Wenn du ein DataFrame hast:
# trades_df = extract_trades_for_db(root, logger)   # dein DataFrame
# clean_df = diagnose_and_clean(trades_df)

# 2) Wenn du list[dict] hast:
# trades_list = [...]  # z.B. vorher .to_dict('records') oder so
# clean_list = diagnose_and_clean(trades_list)

# Nach der Reinigung: falls DataFrame, dann direkt to_sql; falls list[dict], konvertieren:
# if list -> df
# clean_df = pd.DataFrame(clean_list)
# clean_df.to_sql(...)

def diagnose_field(df, field):
    if field not in df.columns:
        print(f"⚠️ Feld '{field}' existiert nicht im DataFrame.")
        return

    # Zeilen mit NaN oder None im angegebenen Feld
    mask = df[field].isna()
    rows_with_nan = df[mask]

    print(f"\n🔎 Diagnose für Feld: '{field}'")
    print(f"→ Gesamtzeilen: {len(df)}")
    print(f"→ Fehlende Werte (NaN/None): {mask.sum()}")

    if mask.sum() > 0:
        print("\nBeispiele betroffener Zeilen (max. 10):")
        print(rows_with_nan.head(10))
    else:
        print("✅ Keine fehlenden Werte gefunden.")


# Beispiel-Aufruf:
# diagnose_field(trades_df, "opt_strategy")

def calculate_hold_metrics(open_dt: datetime, close_dt: datetime):
    """
    Berechnet alle zeitrelevanten Metriken für einen geschlossenen Trade.
    """
    if not (isinstance(open_dt, datetime) and isinstance(close_dt, datetime)):
        return 0, "N/A"

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

