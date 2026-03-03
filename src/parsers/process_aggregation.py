import pandas as pd
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from src.logger_setup import print_log
from src.config import MAX_TRADE_IDS


def aggregate_trades(trades_in, logger):
    df = trades_in.copy()

    # --- 1: Nur ExchTrades berücksichtigen ---
    df_ex = df[df["transactionType"] == "ExchTrade"].copy()
    # df_book = df[df["transactionType"] == "BookTrade"].copy()

    group_cols = ["ibOrderID", "buySell", "transactionType"]

    # --- 2: Order-IDs mit mehreren Ausführungen finden ---
    multi_exec_orders = (
        df_ex.groupby(group_cols)
        .size()
        .reset_index(name="count")
    )
    multi_exec_orders = multi_exec_orders[multi_exec_orders["count"] > 1]

    print_log(logger, f"Anzahl Order-IDs mit mehreren Ausführungen: {len(multi_exec_orders)}")

    # --- Wenn keine Aggregationen nötig sind ---
    if len(multi_exec_orders) == 0:
        return df

    # --- 3: Aggregation definieren ---
    def agg_tradeIDs(x):
        ids = x["tradeID"].dropna().astype(str).tolist()
        if len(ids) <= MAX_TRADE_IDS:
            return ",".join(ids)
        else:
            return ",".join(ids[:MAX_TRADE_IDS]) + f" (+{len(ids) - MAX_TRADE_IDS} more)"

    df_agg = (
        df_ex.groupby(group_cols, group_keys=False)
        .apply(lambda x: pd.Series({
            "ibOrderID": x.name[0],  # kommt aus der Gruppierung, ist Index
            "symID": x["symID"].iloc[0],
            "assetCategory": x["assetCategory"].iloc[0],
            "subCategory": x["subCategory"].iloc[0],
            "symbol": x["symbol"].iloc[0],
            "description": x["description"].iloc[0],
            "underlyingSymbol": x["underlyingSymbol"].iloc[0],
            "underlyingConid": x["underlyingConid"].iloc[0],
            "conid": x["conid"].iloc[0],
            "currency": x["currency"].iloc[0],
            "multiplier": x["multiplier"].iloc[0],
            "strike": x["strike"].iloc[0],
            "expiry": x["expiry"].iloc[0],
            "putCall": x["putCall"].iloc[0],
            "buySell": x.name[1],  # kommt aus der Gruppierung, ist Index
            "tradeDate": x["tradeDate"].min(),
            "tradeTime": x["tradeTime"].min(),
            "quantity": safe_sum_decimal(x["quantity"]),
            "tradePrice": compute_weighted_price_decimal(x),
            "netCash": safe_sum_decimal(x["netCash"]),
            "proceeds": safe_sum_decimal(x["proceeds"]),
            "ibCommission": safe_sum_decimal(x["ibCommission"]),
            "strategy": x["strategy"].iloc[0],
            "status": x["status"].iloc[0],
            "tradeID": agg_tradeIDs(x),
            "source": x["source"].iloc[0],
            "is_split": x["is_split"].iloc[0],
            "split_type": x["split_type"].iloc[0],
            "actionID": x["actionID"].iloc[0],
            "linkID": x["linkID"].iloc[0],
            "opt_strategy": x["opt_strategy"].iloc[0],
            "opt_strategyName": x["opt_strategyName"].iloc[0],
            "opt_strategyID": x["opt_strategyID"].iloc[0],
            # "environment": x["environment"].iloc[0],  wird erst später gesetzt
            "checksum": x["checksum"].iloc[0],
            "processed": x["processed"].iloc[0],
            "datetime": x["datetime"].iloc[0],
            "transactionType": "ExchTrade",
        }),
               include_groups=False
               )
        .reset_index(drop=True)
    )

    # --- 5: Alte Einzel-Ausführungen entfernen ---
    remove_mask = df["ibOrderID"].isin(df_agg["ibOrderID"])
    df_clean = df[~remove_mask].copy()

    # --- 6: Aggregierte hinzufügen ---
    result = pd.concat([df_clean, df_agg], ignore_index=True)

    return result


def compute_weighted_price_decimal(x: pd.DataFrame):
    """Berechne gewichteten Durchschnittspreis mit Decimal-Präzision."""
    total_value = Decimal('0.00000000')
    total_qty = Decimal('0')

    for _, row in x.iterrows():
        # Werte sicher zu Decimal konvertieren (via String!)
        qty = Decimal(str(row['quantity'])) if pd.notnull(row['quantity']) else Decimal('0')
        price = Decimal(str(row['tradePrice'])) if pd.notnull(row['tradePrice']) else Decimal('0')

        total_value += qty * price
        total_qty += qty

    if total_qty == 0:
        return None

    # Ergebnis berechnen
    weighted_price = total_value / total_qty

    # Optional: Auf 4 oder 6 Stellen runden für die Datenbank
    return weighted_price.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


def safe_sum_decimal(series: pd.Series):
    """Summiert Werte als Decimal, um Fließkommafehler zu vermeiden."""
    total = Decimal('0.0000')

    for val in series:
        if pd.isna(val) or val is None:
            continue
        try:
            # Falls der Wert bereits Decimal ist, direkt addieren
            # Falls es ein String/Float ist, erst konvertieren
            total += Decimal(str(val))
        except (InvalidOperation, ValueError):
            continue

    return total
