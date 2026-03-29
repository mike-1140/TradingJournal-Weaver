# src/parsers/flex_parser.py
# -------------------------------------------------------------
# Sequentielle Verarbeitung von IBKR FlexQuery-Dateien
# - Jedes FlexStatement wird einzeln eingelesen, verarbeitet und gespeichert
# -------------------------------------------------------------

import xml.etree.ElementTree as ET
from typing import Any

import pandas as pd
import uuid
from decimal import Decimal
from src.utils.div_utils import compute_checksum, print_selected, to_decimal
from src.parsers.day_trade_processor import extract_trades_for_db, extract_optioneae_for_db, \
    extract_corporateaction_for_db
from src.parsers.option_strategies import detect_strategies
from src.logger_setup import print_log
from src.config import TABLE_TRADES_RAW, TABLE_TRADES_FX
from src.book_trades import handle_booktrades
from src.options_pnl import calculate_pnl, get_position_summary


# Prüfung, ob XML-Element leer ist
# Ein XML-Element gilt als leer, wenn:
# es keine Kindknoten hat → len(elem) == 0
# und keine echte Text-Information → elem.text ist None oder nur whitespace
def is_empty(elem):
    if elem is None:
        return True
    # leer, wenn KEINE Unterelemente und keine Text (oder nur Whitespace)
    return (len(elem) == 0) and (not elem.text or elem.text.strip() == "")


def process_flex_file(xml_path, db, repo, logger, environment: str) -> int | tuple[int | Any, int]:
    """
    Liest eine FlexQuery-XML-Datei und verarbeitet JEDES <FlexStatement> einzeln.
    - liest nur die Trades aus dem jeweiligen Statement
    - berechnet Checksums
    - prüft Duplikate gegen DB
    - schreibt neue Datensätze sofort in die Datenbank
    """

    logger.info(f"📂 Starte Verarbeitung der FlexQuery-Datei: {xml_path.name}")
    env_up = environment.upper()

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        logger.error(f"❌ Fehler beim Einlesen von {xml_path.name}: {e}")
        return 0

    flex_statements = root.findall(".//FlexStatement")
    if not flex_statements:
        logger.warning(f"⚠️ Keine <FlexStatement>-Sektionen in {xml_path.name}.")
        return 0

    total_inserted = 0
    some_entries = 0

    # ➡️ Jede FlexStatement-Sektion separat verarbeiten
    for idx, stmt in enumerate(flex_statements, start=1):
        stmt_date = stmt.get("toDate") or stmt.get("fromDate")
        account_id = stmt.get("accountId", "UNKNOWN")

        logger.info(f"🧾 [{idx}/{len(flex_statements)}] Verarbeite Statement "
                    f"{stmt_date or 'Unbekannt'} ({account_id}) ...")

        # prüfe, ob das Statement leer ist
        # trades = stmt.find("Trades")
        # option_eae = stmt.find("OptionEAE")
        # corp = stmt.find("CorporateActions")
        # if is_empty(trades):
        #     continue

        # === 1️⃣ Trades extrahieren ===
        df_trades, df_cashfx = extract_trades_for_db(stmt, logger)
        df_eae = extract_optioneae_for_db(stmt, logger)
        df_ca = extract_corporateaction_for_db(stmt, logger)

        # === 2️⃣ verarbeite die Trades (vor allem die BOOKTRADES)
        trades_df = process_flexquery(df_trades, df_eae, df_ca, logger)
        # print_selected(trades_new_df,'trades_new_df',["assetCategory", "symbol", "tradeTime", "quantity", "tradePrice", "netCash", "ibCommission"])

        # === 3️⃣ verarbeite die FX-Trades
        # print_selected(df_cashfx,'df_cashfx', ["assetCategory", "symbol"])
        cashfx_df = process_flexquery_fx(df_cashfx)

        # aktuallisiere die Datenbank
        if not trades_df.empty:
            some_entries = 1
            # pairs = trades_df[["symbol", "assetCategory"]].drop_duplicates()
            # Gruppiert nach den Key-Spalten und nimmt den ersten Wert der restlichen Spalten
            pairs = trades_df.groupby(["symbol", "assetCategory"]).first().reset_index()
            # Alle bekannten Symbole abfragen
            results = repo.get_symbols_bulk(pairs["symbol"].tolist(), pairs["assetCategory"].tolist())
            # results könnte z. B. eine Liste von Dicts sein: [{"symbol":"AAPL","assetCategory":"EQ","id":123}, ...]
            symbol_map = {(r["symbol"], r["assetCategory"]): r["id"] for r in results}

            for _, row in pairs.iterrows():
                key = (row["symbol"], row["assetCategory"])
                if key not in symbol_map:
                    new_id = repo.insert_symbol(row["symbol"], row["assetCategory"], row["isin"],
                                                row["underlyingSymbol"], row["conid"], row["underlyingConid"], env_up)
                    symbol_map[key] = new_id

            trades_df["symID"] = trades_df.apply(
                lambda _row: symbol_map[(_row["symbol"], _row["assetCategory"])], axis=1
            )
            trades_df["environment"] = env_up  # setzt automatisch MONEY | PAPER | TEST

            # print(trades_df[["symbol", "multiplier", "transactionType", "quantity", "strike", "status", "netCash",
            #                  "ibCommission", "opt_strategy", "opt_strategyName", "opt_strategyID"]])
            # print(cashfx_df[
            #           ["symbol", "baseCurrency", "baseAmount", "quoteCurrency", "fxRate", "commission", "dateTime"]])
            # checksums in Liste umwandeln, checksums aus DB holen, und die nicht existierenden Zeilen ausgeben
            checksums = trades_df["checksum"].unique().tolist()
            existing = db.get_existing_trades_checksums(checksums)
            new_trades_df = trades_df[~trades_df["checksum"].isin(existing)].copy()
            num_inserted = 0

            if len(new_trades_df) > 0:  # nur wenn neue Daten zum einfügen sind
                num_inserted = db.insert_dataframe(new_trades_df, TABLE_TRADES_RAW)
                total_inserted += num_inserted
            print_log(logger, f"{num_inserted} neue Trades importiert")

        if not cashfx_df.empty:
            some_entries = 1
            cashfx_df["environment"] = env_up
            checksums = cashfx_df["checksum"].unique().tolist()
            existing = db.get_existing_fx_checksums(checksums)
            new_trades_df = cashfx_df[~cashfx_df["checksum"].isin(existing)].copy()
            num_inserted = 0
            if len(new_trades_df) > 0:  # nur wenn neue Daten zum einfügen sind
                num_inserted = db.insert_dataframe(new_trades_df, TABLE_TRADES_FX)
                total_inserted += num_inserted
            print_log(logger, f"{num_inserted} neue FX-Trades importiert")

    logger.info(f"📊 Datei {xml_path.name}: {total_inserted} neue Trades insgesamt importiert.")
    return total_inserted, some_entries


def process_flexquery(trades_in, eae_in, ca_in, logger):
    # 1. Initialisierung: Starte mit einer leeren Liste für alle Teile
    all_fragments = []

    # --- TEIL A: TRADES VERARBEITEN ---
    if trades_in is not None and not trades_in.empty:
        trades_processed = trades_in.copy()

        # Hilfsfunktion für Aggregation (wie zuvor besprochen)
        def aggregate_trades(d_f, category):
            mask = (d_f['assetCategory'] == category) & (d_f['transactionType'] == 'ExchTrade')
            to_agg = d_f[mask].copy()
            if to_agg.empty:
                return d_f

            others = d_f[~mask].copy()
            group_cols = ['conid', 'symbol', 'buySell', 'ibOrderID']
            to_agg['volume'] = to_agg['tradePrice'] * to_agg['quantity']

            # Dynamische Regeln für alle Spalten
            agg_rules = {col: 'first' for col in to_agg.columns if col not in group_cols}
            agg_rules.update({
                'quantity': 'sum',
                'netCash': 'sum',
                'proceeds': 'sum',
                'ibCommission': 'sum',
                'volume': 'sum'
            })

            aggregated = to_agg.groupby(group_cols, as_index=False).agg(agg_rules)
            aggregated['tradePrice'] = aggregated['volume'] / aggregated['quantity']
            return pd.concat([others, aggregated.drop(columns=['volume'])], ignore_index=True)

        # Aggregationen durchführen
        trades_processed = aggregate_trades(trades_processed, 'STK')
        # print_selected(trades_processed, 'trades_processed_STK',
        #                ["symbol", "multiplier", "transactionType", "buySell", "quantity", "datetime", "status", "linkID"])
        trades_processed = aggregate_trades(trades_processed, 'OPT')
        # print_selected(trades_processed, 'trades_processed_OPT',
        #                ["symbol", "multiplier", "transactionType", "buySell", "quantity", "datetime", "status", "linkID"])

        # Strategien erkennen
        trades_processed = detect_strategies(trades_processed)

        # EAE / Booktrades Logik (nur wenn EAE Daten da sind)
        if eae_in is not None and not eae_in.empty:
            eae_opt = eae_in.query('assetCategory == "OPT"').copy()
            is_book = trades_processed['transactionType'] == "BookTrade"
            book_trades = trades_processed[is_book].copy()
            normal_trades = trades_processed[~is_book].copy()

            handled_books = handle_booktrades(book_trades, eae_opt, "dateTime", "dateTime", 1, logger)

            trades_processed = pd.concat([handled_books, normal_trades], ignore_index=True)
            # print_selected(trades_processed, 'trades_processed',
            #                ["symbol", "multiplier", "transactionType", "quantity", "strike", "status", "linkID"])

            print_log(logger, f"{len(handled_books)} Booktrades verarbeitet")

        all_fragments.append(trades_processed)
    else:
        print_log(logger, "Keine regulären Trades zur Verarbeitung.")

    # --- TEIL B: CORPORATE ACTIONS VERARBEITEN ---
    if ca_in is not None and not ca_in.empty:
        print_log(logger, f"{len(ca_in)} Corporate Actions gefunden.")
        ca_processed = sort_corporate_actions(ca_in.copy())
        all_fragments.append(ca_processed)

    # --- TEIL C: ZUSAMMENFÜHRUNG ---
    if not all_fragments:
        # Falls absolut gar nichts da ist, leeres DF mit korrekten Spalten zurückgeben
        return pd.DataFrame(columns=trades_in.columns) if trades_in is not None else pd.DataFrame()

    # Definiere deine gewünschten Spalten
    desired_columns = ['actionID', 'assetCategory', 'buySell', 'checksum', 'conid', 'currency',
                       'dateTime', 'description', 'expiry', 'fxRateToBase', 'ibCommission', 'ibOrderID', 'is_split',
                       'isin', 'linkID', 'multiplier', 'netCash', 'opt_strategy', 'opt_strategyID',
                       'opt_strategyName', 'proceeds', 'processed', 'putCall', 'quantity', 'source',
                       'split_type', 'status', 'strategy', 'strike', 'subCategory', 'symID', 'fifoPnlRealized',
                       'symbol', 'tradeID', 'tradePrice', 'transactionType', 'underlyingConid', 'underlyingSymbol', 'openCloseIndicator']

    # Jedes Fragment auf diese Spalten zuschneiden (fehlende werden NaN)
    reindexed_dfs = []
    cleaned_dfs = []

    for fragment in all_fragments:
        # 1. Prüfen, ob das Fragment ein DataFrame ist
        if isinstance(fragment, pd.DataFrame):
            if not fragment.empty:
                cleaned_dfs.append(fragment)

        # 2. Prüfen, ob es eine Liste ist (wie in deiner Anzeige oben)
        elif isinstance(fragment, list):
            if len(fragment) > 1:  # Muss mindestens Header und eine Datenzeile haben
                columns = fragment[0]
                # Filtere leere Listen-Elemente innerhalb der Daten aus
                data = [d for d in fragment[1:] if isinstance(d, list) and len(d) > 0]

                if data:
                    df_temp = pd.DataFrame(data, columns=columns)
                    cleaned_dfs.append(df_temp)

    for df in cleaned_dfs:
        if 'expiry' not in df.columns:
            # Erstelle die Spalte leer, aber mit festem Datentyp (Objekt/String)
            df['expiry'] = None
        df['expiry'] = df['expiry'].astype(str)
        # reindex fügt fehlende Spalten hinzu und entfernt überschüssige
        reindexed_dfs.append(df.reindex(columns=desired_columns))

    trades_out = pd.concat(reindexed_dfs, ignore_index=True)
    trades_out = trades_out.reset_index(drop=True)

    # --- TEIL D: ABSCHLUSSARBEITEN (PnL, Checksumme, ...) ---
    # Sicherstellen, dass die Checksumme für alles (Trades + CAs) berechnet wird
    # berechne jetzt PnL für alles
    trades_out = calculate_pnl(trades_out, logger)
    summary = get_position_summary(trades_out, logger)
    # print_selected(summary, 'summary',
    #                ['symbol', 'total_realized_pnl', 'trade_count', 'status_types'])
    if summary.empty:
        trades_out["profit"] = to_decimal('0.0')
    else:
        trades_out["profit"] = summary["total_realized_pnl"]
    trades_out["checksum"] = trades_out.apply(compute_checksum, axis=1)
    trades_out['dateTime'] = pd.to_datetime(trades_out['dateTime'], errors='coerce')
    return trades_out


def sort_corporate_actions(df):
    if df.empty:
        return df

    df = df.copy()

    # -----------------------------
    # STOCK SPLITS
    # -----------------------------
    stk = df[df["assetCategory"] == "STK"].copy()
    if not stk.empty:
        stk["is_old"] = stk["symbol"].str.endswith(".OLD").astype(int)
        stk["is_negative"] = (stk["quantity"] < 0).astype(int)

        stk = stk.sort_values(
            by=["actionID", "is_old", "is_negative", "dateTime"],
            ascending=[True, False, False, True],
            kind="mergesort"
        ).drop(columns=["is_old", "is_negative"])

    # -----------------------------
    # OPTION SPLITS
    # -----------------------------
    opt = df[df["assetCategory"] == "OPT"].copy()
    if not opt.empty:
        # 2. Hilfskolonnen für die Sortierung erstellen
        # Wir nutzen Decimal(str(x)) für den Strike, um exakt zu bleiben
        opt["is_negative"] = (opt["quantity"] < 0).astype(int)

        # opt["strike_val"] = pd.to_numeric(opt["strike"], errors="coerce").fillna(0)
        opt["strike_val"] = opt["strike"].apply(
            lambda x: Decimal(str(x)) if pd.notnull(x) and str(x).strip() != "" else Decimal('0')
        )
        # 3. Sortierung (Decimal-Objekte werden korrekt nach Größe sortiert)
        opt = opt.sort_values(
            by=["actionID", "is_negative", "strike_val"],
            ascending=[True, False, False],
            kind="mergesort"
        )
        # 4. Aufräumen
        opt = opt.drop(columns=["is_negative", "strike_val"])

    # -----------------------------
    # Alles wieder zusammenführen
    # -----------------------------
    df_sorted = pd.concat([stk, opt], ignore_index=True)

    return df_sorted.reset_index(drop=True)


def process_flexquery_fx(df_cashfx):
    df_cashfx = df_cashfx.copy()
    # print_log(logger, f"{len(df_cashfx)} neue Trades in {xml_file} gefunden")
    # Calculat the checksum for every row
    df_cashfx["checksum"] = df_cashfx.apply(compute_checksum, axis=1)

    return df_cashfx


def handle_booktrades_old(trades, eae, date_col_trade, date_col_eae, days_tolerance, logger):
    trades = trades.copy()
    eae = eae.copy()

    # Initialisierung von Hilfsspalten
    for col in ["status", "linkID", "isDummy", "originalIndex", "assignedEaeType"]:
        if col not in trades.columns:
            trades[col] = None

    # Datumskonvertierung
    trades[date_col_trade] = pd.to_datetime(trades[date_col_trade], errors="coerce")
    eae[date_col_eae] = pd.to_datetime(eae[date_col_eae], errors="coerce")

    # Vorbereitung für Merging
    trades["conid_str"] = trades["conid"].astype(str).replace(['nan', 'None', '<NA>'], '')
    eae["conid_str"] = eae["conid"].astype(str).replace(['nan', 'None', '<NA>'], '')

    # ERSTES Merging (nur zur Analyse)
    merged = pd.merge(
        trades.reset_index(),
        eae,
        left_on=["conid_str", "assetCategory", "currency"],
        right_on=["conid_str", "assetCategory", "currency"],
        suffixes=("_t", "_e")
    )

    # Zeitfilter
    merged = merged[
        (merged[f"{date_col_trade}_t"] - merged[f"{date_col_eae}_e"]).abs() <= pd.Timedelta(days=days_tolerance)
        ]

    type_col = "transactionType_e" if "transactionType_e" in merged.columns else "transactionType"

    # DUMMY-TRADES ERZEUGEN UND TYP ZUWEISEN
    dummy_trades = []
    next_dummy_idx = trades.index.max() + 1 if len(trades) > 0 else 0

    for t_idx, grp in merged.groupby("index"):
        possible_types = grp[type_col].unique().tolist()

        # Wenn mehr als ein Booktrade-Typ: Dummy-Trades erzeugen
        if len(possible_types) > 1:
            logger.info(f"Trade {t_idx}: Mehrere Booktrades gefunden ({possible_types}), erzeuge Dummy-Trades")

            # Priorisierung für Original-Trade: Assignment > Cash Settlement > Expiration
            if "Assignment" in possible_types:
                original_type = "Assignment"
                remaining_types = [t for t in possible_types if t != "Assignment"]
            elif "Cash Settlement" in possible_types:
                original_type = "Cash Settlement"
                remaining_types = [t for t in possible_types if t != "Cash Settlement"]
            else:
                original_type = possible_types[0]
                remaining_types = possible_types[1:]

            # Original-Trade bekommt den ersten Typ zugewiesen
            trades.loc[t_idx, "assignedEaeType"] = original_type

            # Für jeden weiteren Typ einen Dummy erzeugen
            for trans_type in remaining_types:
                dummy = trades.loc[t_idx].copy()
                dummy["isDummy"] = True
                dummy["originalIndex"] = t_idx
                dummy["assignedEaeType"] = trans_type  # WICHTIG: Typ-Zuweisung

                row_cs = grp[grp[type_col] == "Cash Settlement"].iloc[0]
                dummy["proceeds"] = row_cs.get("proceeds_e", 0)

                dummy["quantity"] = 0
                dummy.name = next_dummy_idx
                dummy_trades.append(dummy)
                next_dummy_idx += 1
        else:
            # Nur ein Booktrade-Typ: einfach zuweisen
            trades.loc[t_idx, "assignedEaeType"] = possible_types[0] if possible_types else None

    # Dummy-Trades hinzufügen
    if dummy_trades:
        dummy_df = pd.DataFrame(dummy_trades)
        trades = pd.concat([trades, dummy_df], ignore_index=False)
        trades["conid_str"] = trades["conid"].astype(str).replace(['nan', 'None', '<NA>'], '')

    # ZWEITES Merging - diesmal MIT Typ-Filter
    merged = pd.merge(
        trades.reset_index(),
        eae,
        left_on=["conid_str", "assetCategory", "currency"],
        right_on=["conid_str", "assetCategory", "currency"],
        suffixes=("_t", "_e")
    )

    # Zeitfilter
    merged = merged[
        (merged[f"{date_col_trade}_t"] - merged[f"{date_col_eae}_e"]).abs() <= pd.Timedelta(days=days_tolerance)
        ]

    # NEU: Filtere nach zugewiesenem Typ
    type_col = "transactionType_e" if "transactionType_e" in merged.columns else "transactionType"
    assignedType_col = "assignedEaeType_t" if "assignedEaeType_t" in merged.columns else "assignedEaeType"

    # Nur Zeilen behalten, wo der EAE-Typ zum zugewiesenen Typ passt
    merged = merged[merged[type_col] == merged[assignedType_col]]

    used_stk_indices = set()

    # VERARBEITUNG - jetzt hat jeder Trade genau EINEN passenden Booktrade
    for t_idx, grp in merged.groupby("index"):
        if len(grp) == 0:
            continue

        type_col = "transactionType_e" if "transactionType_e" in grp.columns else "transactionType"
        underlyingConid_col = "underlyingConid_e" if "underlyingConid_e" in grp.columns else "underlyingConid"
        quantity_col = "quantity_e" if "quantity_e" in grp.columns else "quantity"
        multiplier_col = "multiplier_e" if "multiplier_e" in grp.columns else "multiplier"

        # Jetzt sollte nur noch EIN Typ vorhanden sein
        selected_type = grp[type_col].iloc[0]
        link_id = str(uuid.uuid4())

        # URSPRÜNGLICHE IF/ELIF LOGIK
        if selected_type == "Expiration":
            trades.loc[t_idx, "status"] = "Expired"

        elif selected_type == "Cash Settlement":
            trades.loc[t_idx, "status"] = "CashSettled"
            row_cs = grp.iloc[0]
            trades.loc[t_idx, "netCash"] = row_cs.get("proceeds", 0)

        elif selected_type == "Assignment":
            trades.loc[t_idx, "status"] = "Assigned"
            trades.loc[t_idx, "linkID"] = link_id

            assignment_info = grp.iloc[0]
            u_conid = str(assignment_info.get(underlyingConid_col, ""))
            target_qty = abs(assignment_info.get(quantity_col, 0) * assignment_info.get(multiplier_col, 1))

            stk_mask = (
                    (trades["assetCategory"] == "STK") &
                    (trades["conid"].astype(str) == u_conid) &
                    (~trades.index.isin(used_stk_indices)) &
                    (abs(trades["quantity"]) == target_qty)
            )
            stk_candidates = trades[stk_mask]

            if not stk_candidates.empty:
                stk_idx = (stk_candidates[date_col_trade] - assignment_info[f"{date_col_eae}_e"]).abs().idxmin()
                trades.loc[stk_idx, "linkID"] = link_id
                trades.loc[stk_idx, "status"] = "Assigned"
                used_stk_indices.add(stk_idx)
        else:
            trades.loc[t_idx, "status"] = "Unknown"

    return trades.drop(columns=["conid_str"])
