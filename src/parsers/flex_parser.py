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
from src.utils.div_utils import compute_checksum, to_decimal
from src.parsers.day_trade_processor import extract_trades_for_db, extract_optioneae_for_db, \
    extract_corporateaction_for_db
from src.parsers.option_strategies import detect_strategies
from src.logger_setup import print_log
from src.config import TABLE_TRADES_RAW, TABLE_TRADES_FX
from src.trade_enums import AssetCategory, TransactionType
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

        # === 1️⃣ Trades extrahieren ===
        df_trades, df_cashfx = extract_trades_for_db(stmt, logger)
        df_eae = extract_optioneae_for_db(stmt, logger)
        df_ca = extract_corporateaction_for_db(stmt, logger)

        # === 2️⃣ verarbeite die Trades (vor allem die BOOKTRADES)
        trades_df = process_flexquery(df_trades, df_eae, df_ca, logger)

        # === 3️⃣ verarbeite die FX-Trades
        cashfx_df = process_flexquery_fx(df_cashfx)

        # aktuallisiere die Datenbank
        if not trades_df.empty:
            some_entries = 1
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
            mask = (d_f['assetCategory'] == category) & (d_f['transactionType'] == TransactionType.EXCH_TRADE)
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
        trades_processed = aggregate_trades(trades_processed, AssetCategory.STOCK)
        trades_processed = aggregate_trades(trades_processed, AssetCategory.OPTION)

        # Strategien erkennen (dateTime muss datetime64 sein für .dt-Accessor)
        trades_processed['dateTime'] = pd.to_datetime(trades_processed['dateTime'], errors='coerce')
        trades_processed = detect_strategies(trades_processed)

        # EAE / Booktrades Logik (nur wenn EAE Daten da sind)
        if eae_in is not None and not eae_in.empty:
            eae_opt = eae_in[eae_in['assetCategory'] == AssetCategory.OPTION].copy()
            is_book = trades_processed['transactionType'] == TransactionType.BOOK_TRADE
            book_trades = trades_processed[is_book].copy()
            normal_trades = trades_processed[~is_book].copy()

            handled_books = handle_booktrades(book_trades, eae_opt, "dateTime", "dateTime", 1, logger)

            trades_processed = pd.concat([handled_books, normal_trades], ignore_index=True)

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
            df['expiry'] = None
        df['expiry'] = df['expiry'].apply(
            lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) and x is not None else None
        )
        reindexed_dfs.append(df.reindex(columns=desired_columns))

    trades_out = pd.concat(reindexed_dfs, ignore_index=True)
    trades_out = trades_out.reset_index(drop=True)

    # --- TEIL D: ABSCHLUSSARBEITEN (PnL, Checksumme, ...) ---
    # Sicherstellen, dass die Checksumme für alles (Trades + CAs) berechnet wird
    # berechne jetzt PnL für alles
    trades_out = calculate_pnl(trades_out, logger)
    summary = get_position_summary(trades_out, logger)
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
    stk = df[df["assetCategory"] == AssetCategory.STOCK].copy()
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
    opt = df[df["assetCategory"] == AssetCategory.OPTION].copy()
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
    df_cashfx["checksum"] = df_cashfx.apply(compute_checksum, axis=1)

    return df_cashfx
