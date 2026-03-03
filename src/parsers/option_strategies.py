# src/parsers/option_strategies.py
# -------------------------------------------------------------
# Erkenne Options-Strategien im DataFrame.
#
#   Primär:  ibOrderID-Gruppierung (gleiche Combo-Order bei IBKR)
#   Fallback: Zeitfenster (3s) für manuell gestaffelte Legs
#
#   Unterstützte Strategien:
#     - Vertical Spread  (gleicher Typ, gleiche Expiry, verschiedener Strike)
#     - Calendar Spread  (gleicher Typ, gleicher Strike, verschiedene Expiry)
#     - Diagonal Spread  (gleicher Typ, verschiedener Strike, verschiedene Expiry)
#     - Straddle         (C+P, gleicher Strike, gleiche Expiry, gleiche Richtung)
#     - Strangle         (C+P, verschiedener Strike, gleiche Expiry, gleiche Richtung)
#     - Call / Put Butterfly (3 Legs, Verhältnis 1:-2:1)
#     - Iron Condor      (4 Legs: 2 Calls + 2 Puts, gleiche Expiry)
# -------------------------------------------------------------
import uuid
import pandas as pd


def _is_valid_order_id(val) -> bool:
    """Prüft ob ein ibOrderID-Wert nutzbar ist (nicht leer/null/0)."""
    if val is None:
        return False
    if isinstance(val, float) and pd.isna(val):
        return False
    return str(val).strip() not in ("", "0", "None", "nan")


def detect_strategies(trades_df: pd.DataFrame) -> pd.DataFrame:
    if trades_df.empty:
        return trades_df

    df = trades_df[trades_df["transactionType"] == "ExchTrade"].copy()
    if df.empty:
        return trades_df

    trades_df = trades_df.copy()
    for col in ["opt_strategy", "opt_strategyID", "opt_strategyName"]:
        if col not in trades_df.columns:
            trades_df[col] = 0 if col == "opt_strategy" else ""

    df["time_cluster"] = df["dateTime"].dt.floor("3s")
    processed_indices = set()

    # ===== PRIMÄR: ibOrderID-Gruppierung =====
    # IBKR vergibt für alle Legs einer Combo-Order dieselbe ibOrderID.
    valid_order_mask = df["ibOrderID"].apply(_is_valid_order_id)

    for order_id, group in df[valid_order_mask].groupby("ibOrderID"):
        opt_group = group[group["assetCategory"] == "OPT"]
        if len(opt_group) < 2:
            continue

        legs_agg = _aggregate_legs(opt_group)
        name = _classify_strategy(legs_agg)

        if name:
            indices = opt_group.index.tolist()
            processed_indices.update(indices)
            strat_id = str(uuid.uuid4())
            trades_df.loc[indices, "opt_strategy"] = 1
            trades_df.loc[indices, "opt_strategyID"] = strat_id
            trades_df.loc[indices, "opt_strategyName"] = name

    # ===== FALLBACK: Zeitfenster-Gruppierung =====
    # Für Legs ohne gemeinsame ibOrderID (manuell gestaffelt).
    unprocessed = df[~df.index.isin(processed_indices)]

    for _, cluster in unprocessed.groupby(["underlyingSymbol", "time_cluster"]):
        opt_cluster = cluster[cluster["assetCategory"] == "OPT"]
        if len(opt_cluster) < 2:
            continue

        legs_agg = _aggregate_legs(opt_cluster)
        name = _classify_strategy(legs_agg)

        if name:
            indices = opt_cluster.index.tolist()
            strat_id = str(uuid.uuid4())
            trades_df.loc[indices, "opt_strategy"] = 1
            trades_df.loc[indices, "opt_strategyID"] = strat_id
            trades_df.loc[indices, "opt_strategyName"] = name

    return trades_df


def _aggregate_legs(group: pd.DataFrame) -> pd.DataFrame:
    """Aggregiert Partial Fills innerhalb einer Gruppe zu eindeutigen Legs."""
    return group.groupby(["strike", "putCall", "expiry"]).agg(
        quantity=("quantity", "sum"),
        buySell=("buySell", "first"),
    ).reset_index()


def _classify_strategy(legs: pd.DataFrame) -> str:
    """Dispatcher: wählt Klassifikationslogik nach Anzahl der Legs."""
    n = len(legs)
    if n == 2:
        return _classify_2_legs(legs)
    if n == 3:
        return _classify_3_legs(legs)
    if n == 4:
        return _classify_4_legs(legs)
    return ""


def _classify_2_legs(legs: pd.DataFrame) -> str:
    q1, q2 = legs["quantity"].iloc[0], legs["quantity"].iloc[1]
    pc1, pc2 = legs["putCall"].iloc[0], legs["putCall"].iloc[1]
    exp1, exp2 = legs["expiry"].iloc[0], legs["expiry"].iloc[1]
    str1, str2 = legs["strike"].iloc[0], legs["strike"].iloc[1]

    # Ungleiche Mengen = kein Standard-Spread
    if abs(q1) != abs(q2):
        return ""

    same_type = (pc1 == pc2)
    same_expiry = (exp1 == exp2)
    same_strike = (str1 == str2)
    same_dir = (q1 > 0) == (q2 > 0)  # Beide long oder beide short

    if same_type:
        # Spreads: entgegengesetzte Richtungen erforderlich
        if same_dir:
            return ""
        if same_expiry and not same_strike:
            return "Vertical Spread"
        if not same_expiry and same_strike:
            return "Calendar Spread"
        if not same_expiry and not same_strike:
            return "Diagonal Spread"

    else:
        # Straddle / Strangle: gleiche Richtung (beide long oder beide short)
        if not same_dir:
            return ""
        if same_strike and same_expiry:
            return "Straddle"
        if not same_strike and same_expiry:
            return "Strangle"

    return ""


def _classify_3_legs(legs: pd.DataFrame) -> str:
    # Butterfly: alle gleicher Typ (C oder P), gleiche Expiry, Verhältnis 1:-2:1
    if legs["putCall"].nunique() != 1:
        return ""
    if legs["expiry"].nunique() != 1:
        return ""
    if legs["quantity"].sum() != 0:
        return ""

    qtys = sorted(legs["quantity"].abs().tolist())
    if qtys[0] == qtys[1] and qtys[2] == qtys[0] * 2:
        opt_type = legs["putCall"].iloc[0]
        return f"{'Call' if opt_type == 'C' else 'Put'} Butterfly"

    return ""


def _classify_4_legs(legs: pd.DataFrame) -> str:
    # Iron Condor: 2 Calls + 2 Puts, gleiche Expiry, net qty = 0
    # Calls und Puts bilden je einen eigenen Vertical (net qty = 0 pro Seite)
    if legs["quantity"].sum() != 0:
        return ""
    if legs["putCall"].nunique() != 2:
        return ""
    if legs["expiry"].nunique() != 1:
        return ""

    calls = legs[legs["putCall"] == "C"]
    puts = legs[legs["putCall"] == "P"]
    if len(calls) != 2 or len(puts) != 2:
        return ""
    if calls["quantity"].sum() != 0 or puts["quantity"].sum() != 0:
        return ""

    return "Iron Condor"