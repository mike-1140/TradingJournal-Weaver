"""
IBKR Options Booktrade Processing
==================================

Dieses Modul verarbeitet Interactive Brokers FlexQuery Trades und OptionEAE Events
und fügt sie korrekt zusammen.

WICHTIGE KONZEPTE:
-----------------

1. **Booktrades**: IBKR erzeugt automatische "BookTrade" Einträge, wenn Optionen
   expired, assigned oder exercised werden. Diese haben transactionType="BookTrade".

2. **OptionEAE Events**: In separaten OptionEAE-Einträgen wird der Grund für den
   Booktrade dokumentiert (Assignment, Exercise, Expiration, Cash Settlement).

3. **TradeID Matching**:
   - Assignment/Exercise/Expiration Events haben ein tradeID-Feld, das auf den
     entsprechenden Booktrade verweist.
   - Cash Settlement Events haben EIGENE tradeIDs und müssen über conid+datum
     gematched werden.

4. **Mehrere EAE pro Trade**:
   Bei SPX Optionen (Cash Settlement) gibt es ZWEI EAE-Events für einen Booktrade:
   - Assignment/Exercise Event (erklärt den Booktrade)
   - Cash Settlement Event (zeigt den Cashflow)

VERARBEITUNGSLOGIK:
------------------

1. Filtere nur Options-EAE (assetCategory='OPT'), keine Stock-EAE
2. Separiere Cash Settlement Events von anderen EAE-Events
3. Matche Assignment/Exercise/Expiration Events über tradeID
4. Matche Cash Settlement Events separat über conid+datum (nur bei BookTrades)
5. Verarbeite jeden Trade:
   - Bei Assignment: Status setzen, linkID vergeben, Stock-Trade suchen
   - Bei Exercise: Status setzen
   - Bei Expiration: Status setzen
   - Bei Cash Settlement: proceeds übernehmen

BEISPIELE:
---------

**Fall 1: ON - Normale Option mit Assignment (Stock Delivery)**
- ExchTrade: SELL Call Option
- Booktrade: BUY Call Option (schließt Position)
- Booktrade: SELL Stock (Lieferung der Aktien)
- OptionEAE: Assignment (verweist auf Options-Booktrade)
→ Ergebnis: Options-Booktrade status="Assigned" mit linkID, Stock-Trade bekommt gleiche linkID

**Fall 2: SPX - Option mit Cash Settlement**
- ExchTrade: BUY Put Option
- Booktrade: SELL Put Option (schließt Position)
- OptionEAE: Exercise (verweist auf Booktrade)
- OptionEAE: Cash Settlement (eigene tradeID, enthält proceeds)
→ Ergebnis: Booktrade status="Exercised", cashSettlement_proceeds=2819.0

**Fall 3: SPX - Expired Option**
- ExchTrade: SELL Call Option
- Booktrade: BUY Call Option (schließt Position)
- OptionEAE: Expiration (verweist auf Booktrade)
→ Ergebnis: Booktrade status="Expired"
"""

import pandas as pd
import uuid
from src.logger_setup import print_log
from src.utils.div_utils import parse_datetime_flex


def handle_booktrades(trades, eae, date_col_trade, date_col_eae, days_tolerance, logger):
    """
    Verarbeitet IBKR Booktrades und ihre zugehörigen Exercise/Assignment Events (EAE).

    Parameters
    ----------
    trades : pd.DataFrame
        DataFrame mit Trade-Daten aus FlexQuery
        Erwartete Spalten: tradeID, conid, assetCategory, currency, transactionType,
                          quantity, multiplier, underlyingConid, [date_col_trade]

    eae : pd.DataFrame
        DataFrame mit OptionEAE-Daten aus FlexQuery
        Erwartete Spalten: tradeID, conid, assetCategory, currency, transactionType,
                          quantity, multiplier, underlyingConid, proceeds, [date_col_eae]

    date_col_trade : str
        Name der Datumsspalte in trades (z.B. 'dateTime')

    date_col_eae : str
        Name der Datumsspalte in eae (z.B. 'date')

    days_tolerance : int
        Maximale Anzahl Tage Abweichung für Datum-Matching (empfohlen: 7)

    logger : logging.Logger
        Logger-Objekt für Debug-Ausgaben

    Returns
    -------
    pd.DataFrame
        Erweiterter trades DataFrame mit zusätzlichen Spalten:
        - status: "Assigned", "Exercised", "Expired", "CashSettled", "Unknown", oder None
        - linkID: UUID zur Verlinkung von Options- und Stock-Trades (nur bei Assignment)
        - cashSettlement_proceeds: Proceeds aus Cash Settlement Event (bei SPX etc.)

    Examples
    --------
    >>> result = handle_booktrades(
    ...     trades=trades_df,
    ...     eae=eae_df,
    ...     date_col_trade='dateTime',
    ...     date_col_eae='date',
    ...     days_tolerance=7,
    ...     logger=logger
    ... )
    >>>
    >>> # Finde alle assigned Options mit ihren Stock-Trades
    >>> assigned_opts = result[
    ...     (result['assetCategory'] == 'OPT') &
    ...     (result['status'] == 'Assigned')
    ... ]
    >>> for idx, opt in assigned_opts.iterrows():
    ...     link_id = opt['linkID']
    ...     stocks = result[result['linkID'] == link_id]
    ...     print(f"Option {opt['symbol']} -> {len(stocks)} Stock-Trades")
    """
    trades = trades.copy()
    eae = eae.copy()

    # Initialisierung von Hilfsspalten
    for col in ["status", "linkID", "cashSettlement_proceeds"]:
        if col not in trades.columns:
            trades[col] = None

    # Datumskonvertierung — beide IBKR-Formate werden unterstützt
    trades[date_col_trade] = trades[date_col_trade].apply(parse_datetime_flex)
    eae[date_col_eae] = eae[date_col_eae].apply(parse_datetime_flex)

    # Filtere leere EAE-Zeilen und nur Options-EAE (nicht Stock-EAE)
    if 'transactionType' in eae.columns:
        eae = eae[
            (eae['transactionType'].notna()) &
            (eae['assetCategory'] == 'OPT')  # Nur Options-EAE, keine Stock-EAE
            ].copy()

    # logger.info(f"Anzahl Trades: {len(trades)}, Anzahl valide Options-EAE-Events: {len(eae)}")

    # Stelle sicher, dass tradeID ein String ist für beide DataFrames
    if 'tradeID' in trades.columns:
        trades['tradeID_str'] = trades['tradeID'].astype(str)
    if 'tradeID' in eae.columns:
        eae['tradeID_str'] = eae['tradeID'].astype(str)

    # Separate Cash Settlement Events (haben andere tradeIDs)
    cash_settlement_eae = eae[
        eae['transactionType'] == 'Cash Settlement'].copy() if 'transactionType' in eae.columns else pd.DataFrame()
    other_eae = eae[
        eae['transactionType'] != 'Cash Settlement'].copy() if 'transactionType' in eae.columns else eae.copy()

    # logger.info(f"Cash Settlement Events: {len(cash_settlement_eae)}, Andere EAE: {len(other_eae)}")

    # Merge über tradeID für Assignment/Exercise/Expiration (EAE.tradeID -> Trade.tradeID)
    merged = pd.merge(
        trades.reset_index(),
        other_eae,
        left_on='tradeID_str',
        right_on='tradeID_str',
        suffixes=("_t", "_e"),
        how='left'  # Left join: behalte alle Trades, auch ohne EAE
    )

    # logger.info(f"Nach tradeID-Merge: {len(merged)} Zeilen")

    # Merge Cash Settlement Events über conid + symbol + datum
    if len(cash_settlement_eae) > 0:
        # Prepare für merge über conid
        cash_settlement_eae['conid_str'] = cash_settlement_eae['conid'].astype(str).replace(['nan', 'None', '<NA>'], '')

        # Nur BookTrades für Cash Settlement matchen
        booktrades = trades[trades['transactionType'] == 'BookTrade'].copy()

        # Merge mit Trades
        cs_merged = pd.merge(
            booktrades.reset_index(),
            cash_settlement_eae,
            left_on='conid',
            right_on='conid',
            suffixes=("_t", "_cs"),
            how='inner'
        )

        # Zeitfilter für Cash Settlement
        if len(cs_merged) > 0:
            # Nach Merge haben wir Suffixe: _t und _cs
            date_col_t = f"{date_col_trade}_t" if f"{date_col_trade}_t" in cs_merged.columns else date_col_trade
            date_col_cs = f"{date_col_eae}_cs" if f"{date_col_eae}_cs" in cs_merged.columns else date_col_eae
            cs_merged = cs_merged[
                (cs_merged[date_col_t] - cs_merged[date_col_cs]).abs() <= pd.Timedelta(days=days_tolerance)
                ]

            # logger.info(f"Cash Settlement Matches gefunden: {len(cs_merged)}")

            # Füge Cash Settlement zu merged hinzu
            if len(cs_merged) > 0:
                # Rename columns to match merged structure
                cs_merged = cs_merged.rename(columns={
                    col: col.replace('_cs', '_e') for col in cs_merged.columns if col.endswith('_cs')
                })
                merged = pd.concat([merged, cs_merged], ignore_index=True)
                # logger.info(f"Nach CS-Merge: {len(merged)} Zeilen gesamt")

    # Filtere nur Zeilen mit validen EAE-Events
    type_col = "transactionType_e" if "transactionType_e" in merged.columns else "transactionType"
    merged_with_eae = merged[merged[type_col].notna()].copy()

    # logger.info(f"Zeilen mit EAE-Events: {len(merged_with_eae)}")

    used_stk_indices = set()

    # Verarbeitung: Gruppiere nach Trade-Index
    for t_idx, grp in merged_with_eae.groupby("index"):
        if len(grp) == 0:
            continue

        # Hole alle EAE-Typen für diesen Trade
        eae_types = grp[type_col].unique().tolist()

        # logger.info(f"Trade {t_idx}: Gefundene EAE-Typen: {eae_types}")

        # Bestimme den Haupt-Status basierend auf Priorität
        if "Assignment" in eae_types or "Exercise" in eae_types:
            # Assignment/Exercise gefunden
            status = "Assigned"  # if "Assignment" in eae_types else "Exercised"

            # Finde die Assignment/Exercise Row
            assignment_type = "Assignment" if "Assignment" in eae_types else "Exercise"
            assignment_row = grp[grp[type_col] == assignment_type].iloc[0]

            trades.loc[t_idx, "status"] = status

            # Bei Assignment: Versuche Stock-Trade zu finden und zu verlinken
            if assignment_type == "Assignment":
                underlyingConid_col = "underlyingConid_e" if "underlyingConid_e" in grp.columns else "underlyingConid"
                quantity_col = "quantity_e" if "quantity_e" in grp.columns else "quantity"
                multiplier_col = "multiplier_e" if "multiplier_e" in grp.columns else "multiplier"

                # Prüfe, ob wir einen underlyingConid haben
                u_conid_raw = assignment_row.get(underlyingConid_col, "")
                u_conid = str(int(float(u_conid_raw))) if pd.notna(u_conid_raw) and u_conid_raw not in ['', 'nan',
                                                                                                        'None'] else ""

                # Nur versuchen Stock zu matchen, wenn es einen underlyingConid gibt
                if u_conid and u_conid not in ['', 'nan', 'None']:
                    link_id = str(uuid.uuid4())
                    trades.loc[t_idx, "linkID"] = link_id

                    target_qty = abs(assignment_row.get(quantity_col, 0) * assignment_row.get(multiplier_col, 1))

                    # Suche passenden Stock-Trade - vergleiche conids als Strings ohne Dezimalpunkt
                    def normalize_conid(c):
                        try:
                            return str(int(float(c)))
                        except:
                            return str(c)

                    stk_mask = (
                            (trades["assetCategory"] == "STK") &
                            (trades["conid"].apply(normalize_conid) == u_conid) &
                            (~trades.index.isin(used_stk_indices)) &
                            (abs(trades["quantity"]) == target_qty)
                    )
                    stk_candidates = trades[stk_mask]

                    if not stk_candidates.empty:
                        # Verwende die ursprüngliche EAE-Datum-Spalte
                        eae_date_col = f"{date_col_eae}_e" if f"{date_col_eae}_e" in assignment_row.index else date_col_eae
                        stk_idx = (stk_candidates[date_col_trade] - assignment_row[eae_date_col]).abs().idxmin()
                        trades.loc[stk_idx, "linkID"] = link_id
                        trades.loc[stk_idx, "status"] = "Assigned"
                        used_stk_indices.add(stk_idx)
                        # logger.info(f"  -> Stock-Trade {stk_idx} verlinkt (linkID={link_id})")
                    else:
                        logger.info(
                            f"  -> Kein passender Stock-Trade gefunden (underlyingConid={u_conid}, qty={target_qty})")
                else:
                    logger.info(f"  -> Assignment ohne underlyingConid (vermutlich Cash Settlement)")

            # Prüfe auf Cash Settlement Event
            if "Cash Settlement" in eae_types:
                cs_row = grp[grp[type_col] == "Cash Settlement"].iloc[0]
                proceeds_col = "proceeds_e" if "proceeds_e" in cs_row.index else "proceeds"
                proceeds_value = cs_row.get(proceeds_col, 0)

                trades.loc[t_idx, "cashSettlement_proceeds"] = proceeds_value
                trades.loc[t_idx, "proceeds"] = proceeds_value
                trades.loc[t_idx, "status"] = 'CashSettled'
                # logger.info(f"  -> Cash Settlement: proceeds={proceeds_value}")

        elif "Expiration" in eae_types:
            trades.loc[t_idx, "status"] = "Expired"
            # logger.info(f"  -> Option expired")

        elif "Cash Settlement" in eae_types:
            # Cash Settlement OHNE Assignment/Exercise
            # Bei korrekten IBKR-Daten sollte das nie vorkommen, da Cash Settlement
            # immer zusammen mit Assignment/Exercise auftritt (siehe SPX Beispiel).
            # Dieser Block existiert nur als Fallback für fehlerhafte/unvollständige Daten.
            trades.loc[t_idx, "status"] = "CashSettled"
            cs_row = grp[grp[type_col] == "Cash Settlement"].iloc[0]
            proceeds_col = "proceeds_e" if "proceeds_e" in cs_row.index else "proceeds"
            trades.loc[t_idx, "cashSettlement_proceeds"] = cs_row.get(proceeds_col, 0)
            logger.warning(f"  -> Nur Cash Settlement ohne Assignment/Exercise (ungewöhnlich - prüfe Daten!)")

        else:
            trades.loc[t_idx, "status"] = "Unknown"
            logger.warning(f"  -> Unbekannter EAE-Typ: {eae_types}")

    # Entferne temporäre Spalten
    if 'tradeID_str' in trades.columns:
        trades = trades.drop(columns=['tradeID_str'])

    return trades


"""
DEBUG-VERSION um zu verstehen, warum Assignment/Exercise nicht matchen
"""


def handle_booktrades_debug(trades, eae, date_col_trade, date_col_eae, days_tolerance, logger):
    """
    DEBUG-Version mit ausführlichem Logging
    """
    trades = trades.copy()
    eae = eae.copy()

    # Initialisierung von Hilfsspalten
    for col in ["status", "linkID", "cashSettlement_proceeds"]:
        if col not in trades.columns:
            trades[col] = None

    # Datumskonvertierung — beide IBKR-Formate werden unterstützt
    trades[date_col_trade] = trades[date_col_trade].apply(parse_datetime_flex)
    eae[date_col_eae] = eae[date_col_eae].apply(parse_datetime_flex)

    # DEBUG: Zeige Trade-Typen
    logger.info("=" * 60)
    logger.info("DEBUG: TRADE TRANSACTION TYPES")
    logger.info(trades['transactionType'].value_counts().to_dict())

    # DEBUG: Zeige ein paar Trade-IDs
    logger.info("\nDEBUG: ERSTE 5 TRADE IDs")
    logger.info(trades[['tradeID', 'transactionType', 'symbol']].head().to_string())

    # Filtere leere EAE-Zeilen und nur Options-EAE
    if 'transactionType' in eae.columns:
        eae = eae[
            (eae['transactionType'].notna()) &
            (eae['assetCategory'] == 'OPT')
            ].copy()

    logger.info(f"\nAnzahl Trades: {len(trades)}, Anzahl valide Options-EAE-Events: {len(eae)}")

    # DEBUG: Zeige EAE-Typen
    logger.info("\nDEBUG: EAE TRANSACTION TYPES")
    logger.info(eae['transactionType'].value_counts().to_dict())

    # DEBUG: Zeige ein paar EAE-IDs
    logger.info("\nDEBUG: ERSTE 5 EAE IDs und Typen")
    logger.info(eae[['tradeID', 'transactionType', 'symbol']].head().to_string())

    # Stelle sicher, dass tradeID ein String ist
    if 'tradeID' in trades.columns:
        trades['tradeID_str'] = trades['tradeID'].astype(str)
    if 'tradeID' in eae.columns:
        eae['tradeID_str'] = eae['tradeID'].astype(str)

    # Separate Cash Settlement Events
    cash_settlement_eae = eae[
        eae['transactionType'] == 'Cash Settlement'].copy() if 'transactionType' in eae.columns else pd.DataFrame()
    other_eae = eae[
        eae['transactionType'] != 'Cash Settlement'].copy() if 'transactionType' in eae.columns else eae.copy()

    logger.info(f"\nCash Settlement Events: {len(cash_settlement_eae)}, Andere EAE: {len(other_eae)}")

    # DEBUG: Prüfe ob tradeIDs matchen
    if len(other_eae) > 0:
        logger.info("\nDEBUG: TRADE-ID MATCHING CHECK")
        trade_ids = set(trades['tradeID_str'].unique())
        eae_ids = set(other_eae['tradeID_str'].unique())
        matched_ids = trade_ids & eae_ids
        logger.info(f"Trade IDs: {len(trade_ids)} unique")
        logger.info(f"EAE IDs (Assignment/Exercise): {len(eae_ids)} unique")
        logger.info(f"Matched IDs: {len(matched_ids)}")
        if len(matched_ids) == 0:
            logger.warning("⚠️  KEINE TRADE-IDs MATCHEN!")
            logger.info(f"Beispiel Trade IDs: {list(trade_ids)[:3]}")
            logger.info(f"Beispiel EAE IDs: {list(eae_ids)[:3]}")

    # Merge über tradeID
    merged = pd.merge(
        trades.reset_index(),
        other_eae,
        left_on='tradeID_str',
        right_on='tradeID_str',
        suffixes=("_t", "_e"),
        how='left'
    )

    logger.info(f"\nNach tradeID-Merge: {len(merged)} Zeilen")

    # DEBUG: Wie viele haben EAE?
    type_col = "transactionType_e" if "transactionType_e" in merged.columns else "transactionType"
    has_eae = merged[type_col].notna().sum()
    logger.info(f"Davon mit EAE-Event: {has_eae}")

    # Merge Cash Settlement Events
    if len(cash_settlement_eae) > 0:
        cash_settlement_eae['conid_str'] = cash_settlement_eae['conid'].astype(str).replace(['nan', 'None', '<NA>'], '')

        booktrades = trades[trades['transactionType'] == 'BookTrade'].copy()
        logger.info(f"\nDEBUG: Anzahl BookTrades für CS-Matching: {len(booktrades)}")

        cs_merged = pd.merge(
            booktrades.reset_index(),
            cash_settlement_eae,
            left_on='conid',
            right_on='conid',
            suffixes=("_t", "_cs"),
            how='inner'
        )

        if len(cs_merged) > 0:
            date_col_t = f"{date_col_trade}_t" if f"{date_col_trade}_t" in cs_merged.columns else date_col_trade
            date_col_cs = f"{date_col_eae}_cs" if f"{date_col_eae}_cs" in cs_merged.columns else date_col_eae
            cs_merged = cs_merged[
                (cs_merged[date_col_t] - cs_merged[date_col_cs]).abs() <= pd.Timedelta(days=days_tolerance)
                ]

            logger.info(f"Cash Settlement Matches gefunden: {len(cs_merged)}")

            if len(cs_merged) > 0:
                cs_merged = cs_merged.rename(columns={
                    col: col.replace('_cs', '_e') for col in cs_merged.columns if col.endswith('_cs')
                })
                merged = pd.concat([merged, cs_merged], ignore_index=True)
                logger.info(f"Nach CS-Merge: {len(merged)} Zeilen gesamt")

    # Filtere nur Zeilen mit validen EAE-Events
    type_col = "transactionType_e" if "transactionType_e" in merged.columns else "transactionType"
    merged_with_eae = merged[merged[type_col].notna()].copy()

    logger.info(f"Zeilen mit EAE-Events: {len(merged_with_eae)}")
    logger.info("=" * 60)

    # Ab hier: Rest wie im Original-Code...
    # (Verarbeitung der EAE-Events)

    used_stk_indices = set()

    for t_idx, grp in merged_with_eae.groupby("index"):
        if len(grp) == 0:
            continue

        eae_types = grp[type_col].unique().tolist()

        logger.info(f"Trade {t_idx}: Gefundene EAE-Typen: {eae_types}")

        if "Assignment" in eae_types or "Exercise" in eae_types:
            status = "Assigned" if "Assignment" in eae_types else "Exercised"
            assignment_type = "Assignment" if "Assignment" in eae_types else "Exercise"
            assignment_row = grp[grp[type_col] == assignment_type].iloc[0]

            trades.loc[t_idx, "status"] = status

            if assignment_type == "Assignment":
                underlyingConid_col = "underlyingConid_e" if "underlyingConid_e" in grp.columns else "underlyingConid"
                quantity_col = "quantity_e" if "quantity_e" in grp.columns else "quantity"
                multiplier_col = "multiplier_e" if "multiplier_e" in grp.columns else "multiplier"

                u_conid_raw = assignment_row.get(underlyingConid_col, "")
                u_conid = str(int(float(u_conid_raw))) if pd.notna(u_conid_raw) and u_conid_raw not in ['', 'nan',
                                                                                                        'None'] else ""

                if u_conid and u_conid not in ['', 'nan', 'None']:
                    link_id = str(uuid.uuid4())
                    trades.loc[t_idx, "linkID"] = link_id

                    target_qty = abs(assignment_row.get(quantity_col, 0) * assignment_row.get(multiplier_col, 1))

                    def normalize_conid(c):
                        try:
                            return str(int(float(c)))
                        except:
                            return str(c)

                    stk_mask = (
                            (trades["assetCategory"] == "STK") &
                            (trades["conid"].apply(normalize_conid) == u_conid) &
                            (~trades.index.isin(used_stk_indices)) &
                            (abs(trades["quantity"]) == target_qty)
                    )
                    stk_candidates = trades[stk_mask]

                    if not stk_candidates.empty:
                        eae_date_col = f"{date_col_eae}_e" if f"{date_col_eae}_e" in assignment_row.index else date_col_eae
                        stk_idx = (stk_candidates[date_col_trade] - assignment_row[eae_date_col]).abs().idxmin()
                        trades.loc[stk_idx, "linkID"] = link_id
                        trades.loc[stk_idx, "status"] = "Assigned"
                        used_stk_indices.add(stk_idx)
                        logger.info(f"  -> Stock-Trade {stk_idx} verlinkt (linkID={link_id})")
                    else:
                        logger.info(
                            f"  -> Kein passender Stock-Trade gefunden (underlyingConid={u_conid}, qty={target_qty})")
                else:
                    logger.info(f"  -> Assignment ohne underlyingConid (vermutlich Cash Settlement)")

            if "Cash Settlement" in eae_types:
                cs_row = grp[grp[type_col] == "Cash Settlement"].iloc[0]
                proceeds_col = "proceeds_e" if "proceeds_e" in cs_row.index else "proceeds"
                proceeds_value = cs_row.get(proceeds_col, 0)

                trades.loc[t_idx, "cashSettlement_proceeds"] = proceeds_value
                logger.info(f"  -> Cash Settlement: proceeds={proceeds_value}")

        elif "Expiration" in eae_types:
            trades.loc[t_idx, "status"] = "Expired"
            logger.info(f"  -> Option expired")

        elif "Cash Settlement" in eae_types:
            trades.loc[t_idx, "status"] = "CashSettled"
            cs_row = grp[grp[type_col] == "Cash Settlement"].iloc[0]
            proceeds_col = "proceeds_e" if "proceeds_e" in cs_row.index else "proceeds"
            trades.loc[t_idx, "cashSettlement_proceeds"] = cs_row.get(proceeds_col, 0)
            logger.warning(f"  -> Nur Cash Settlement ohne Assignment/Exercise (ungewöhnlich - prüfe Daten!)")

        else:
            trades.loc[t_idx, "status"] = "Unknown"
            logger.warning(f"  -> Unbekannter EAE-Typ: {eae_types}")

    if 'tradeID_str' in trades.columns:
        trades = trades.drop(columns=['tradeID_str'])

    return trades


# Beispiel-Verwendung
if __name__ == "__main__":
    import logging

    # Logger einrichten
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    logger = logging.getLogger(__name__)

    # Beispiel: Lade Daten aus FlexQuery XML
    # trades_df = parse_flex_trades('flex_query.xml')
    # eae_df = parse_flex_optioneae('flex_query.xml')

    # result = handle_booktrades(
    #     trades=trades_df,
    #     eae=eae_df,
    #     date_col_trade='dateTime',
    #     date_col_eae='date',
    #     days_tolerance=7,
    #     logger=logger
    # )

    print("Siehe Dokumentation oben für Verwendungsbeispiele.")
