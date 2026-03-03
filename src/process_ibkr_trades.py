import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any

from src.config import TABLE_PREFIX, TABLE_TRADES_RAW, TABLE_TRADES_OPEN
from src.db.db_access import DBAccess, TradeRepository
from src.logger_setup import setup_logging, print_log
from src.parsers.inventory_tracker import InventoryTracker
from src.trade_schemas import OpenTradeSchema, ClosedTradeSchema
from src.utils.div_utils import to_decimal
from src.utils.path_utils import get_project_root
from src.utils.progress import ProgressLine

# Logging
log_file = get_project_root() / "log/app.log"
logger, _ = setup_logging('my_app', level="simple", log_file=log_file)
INPUT_DIR = get_project_root() / "input"


def apply_split(old_split, new_split):
    # print(f"Split erkannt: {old_split['symbol']} → {new_split['symbol']}")

    # Berechne neuen Einstand
    factor = abs(new_split["quantity"]) / abs(old_split["quantity"])
    # new_quantity = match["quantity"] * factor
    # new_price = match["tradePrice"] / factor
    # total_cost = match["quantity"] * match["tradePrice"]

    return factor, new_split["symbol"]


def clean_trade_dict(trade_dict, precision=4):
    """
    Konvertiert Felder in Decimal und formatiert sie auf
    eine feste Anzahl von Nachkommastellen.
    """
    decimal_fields = [
        'quantity', 'netCash', 'tradePrice',
        'ibCommission', 'proceeds', 'strike', 'multiplier'
    ]

    # Erzeuge den Quantisierungs-String, z.B. "0.0001" für 4 Stellen
    # Das Format ist "1." gefolgt von '0' * Anzahl Stellen
    quantize_format = Decimal('1.' + '0' * precision) if precision > 0 else Decimal('1')

    cleaned_trade = trade_dict.copy()

    for field in decimal_fields:
        if field in cleaned_trade and cleaned_trade[field] is not None:
            # 1. Konvertierung zu Decimal
            val = to_decimal(cleaned_trade[field])
            # 2. Rundung auf die gewünschten Stellen
            cleaned_trade[field] = val.quantize(quantize_format, rounding=ROUND_HALF_UP)
        else:
            # Standardwert mit der korrekten Präzision
            cleaned_trade[field] = Decimal('0').quantize(quantize_format)

    return cleaned_trade


def process_trades(environment: str, table_pref: str, table_trades_raw):
    """
    Verarbeitet Trades aus der RAW-Tabelle und aktualisiert Open/Closed Trades

    Args:
        environment: Trading Environment ('money', 'paper', 'test')
        table_pref: Tabellen-Prefix für Multi-User Support
        table_trades_raw:
    Raises:
        ValueError: Bei ungültigen Parametern
    """
    # ===== VALIDIERUNG =====
    if not table_pref:
        raise ValueError("table_prefix ist erforderlich")

    environment = environment.lower()
    env_up = environment.upper()

    # ===== INITIALISIERUNG =====
    logger.info("=" * 80)
    logger.info(
        f"Prozessiere Trades für Environment: {env_up} "
        f"({datetime.now().strftime('%Y-%m-%d - %H:%M:%S')})"
    )
    logger.info("=" * 80)

    db = DBAccess(logger, environment, table_pref)
    repo = TradeRepository(db)
    tracker = InventoryTracker(logger, db, table_pref,
                               env_up)  # mit der Initialisierung, werden alle Campaigns geladen.

    # ===== DATEN LADEN =====
    df_raw = db.get_all_raw_trades(env_up, table_trades_raw)

    if df_raw.empty:
        print_log(logger, "Keine neuen Trades zum Verarbeiten gefunden", True)
        return

    total = len(df_raw)
    logger.info(f"{total} Trades zum Bearbeiten gefunden")

    # ===== SPLIT-HANDLING VORBEREITUNG =====
    split_buffer = defaultdict(list)

    # ===== HAUPTSCHLEIFE =====
    progress = ProgressLine(logger)
    progress.start()

    for idx, row in df_raw.iterrows():
        raw_trade = row.to_dict()
        # Daten säubern (Typ-Hoheit für Decimal erzwingen)
        trade = clean_trade_dict(raw_trade)
        trade_id = trade.get('id')

        if not trade_id:
            logger.info(f"Trade ohne ID gefunden (Index {idx}), überspringe")
            continue

        nr = df_raw.index.get_loc(idx) + 1
        symbol = trade.get('symbol', '?')
        asset = trade.get('assetCategory', '')
        dt = str(trade.get('dateTime', ''))[:10]
        progress.update(f"{nr}/{total}  {asset:4}  {symbol:10}  {dt}")

        # Bevor wir den Trade verarbeiten, räumen wir abgelaufene Kampagnen auf
        # basierend auf dem Datum des aktuellen Trades
        tracker._cleanup_expired_campaigns(row['dateTime'])

        # ===== SCHRITT 4: SPLIT-HANDLING =====
        # Split-Trades VOR process_row_and_get_campaign behandeln,
        # damit die Split-Legs keine falschen PENDING/ACTIVE-Zyklen auslösen
        if trade.get("is_split"):
            split_result = _handle_split_trade(trade, split_buffer, repo, table_trades_raw)
            if split_result == 'processed':
                # Campaign-ID direkt aus holdings lesen — ohne Inventory-Update
                split_symbol = trade.get('underlyingSymbol') or trade.get('symbol')
                campaign_id = (tracker.holdings.get(split_symbol) or {}).get('campaign_id')
                process_stock_split(repo, trade, tracker, campaign_id)
                # In-memory Bestand an neuen Faktor anpassen
                if split_symbol in tracker.holdings:
                    factor = float(trade.get('multiplier', 1))
                    tracker.holdings[split_symbol]['shares'] = float(tracker.holdings[split_symbol]['shares']) * factor
            continue  # Split vollständig verarbeitet oder wartet auf zweiten Teil

        campaign_id = tracker.process_row_and_get_campaign(row)

        # ===== SCHRITT 5: TRADE VERARBEITUNG =====
        process_raw_trade(logger, trade, repo, tracker, campaign_id)

    progress.done(f"{total} Trades verarbeitet  [{env_up}]")

    # Nutze das Datum des allerletzten Trades oder das aktuelle Datum
    last_date = datetime.now()
    tracker.finalize(last_date)

    logger.info("=" * 80)
    logger.info("Trade-Verarbeitung abgeschlossen")
    logger.info("=" * 80)


def _handle_split_trade(trade: Dict[str, Any], split_buffer: Dict, repo,
                        table_trades_raw: str) -> str:
    """
    Verarbeitet Split-Trades

    Returns:
        'waiting' wenn auf zweiten Teil gewartet wird
        'processed' wenn Split vollständig verarbeitet wurde
    """
    aid = trade["actionID"]
    split_buffer[aid].append(trade)

    if len(split_buffer[aid]) == 2:
        # Beide Teile vorhanden
        s1, s2 = split_buffer[aid]
        old_split = s1 if s1["quantity"] < 0 else s2
        new_split = s1 if s1["quantity"] > 0 else s2

        # Hier deine apply_split Funktion aufrufen
        trade["multiplier"], trade["symbol"] = apply_split(old_split, new_split)

        print_log(logger,
                  f"Split verarbeitet: {trade.get('multiplier', 'N/A')}x "
                  f"für {trade.get('symbol')}", True
                  )
        del split_buffer[aid]
        return 'processed'
    else:
        # Nur erster Teil, warte auf zweiten
        print_log(logger, f"Split-Trade {aid} - warte auf zweiten Teil", True)
        repo.mark_trade_processed(table_trades_raw, trade["id"])
        return 'waiting'


def process_stock_split(repo, trade, tracker, campaign_id):
    # verarbeite die Splits: alle offenen Trades dieses Symbols sind betroffen

    # Offene Tranchen holen
    factor = trade['multiplier']
    open_tranches = repo.get_open_trades(trade['assetCategory'], trade['symbol'])

    for tr in open_tranches:
        old_qty = to_decimal(tr['quantity'])
        new_qty = old_qty * to_decimal(factor)
        new_price = to_decimal(tr["tradePrice"] / factor)
        added_qty = new_qty - old_qty  # Das ist das Delta für den Ledger

        # 2. Tranche in trades_open aktualisieren
        repo.update_open_trade({
            "id": tr["id"],
            "quantity": new_qty,
            "tradePrice": new_price
        })
        # 3. Ledger informieren (Nur Bestandsänderung, kein Cash!)
        tracker.link_to_campaign_new(
            assetCategory=tr.get("assetCategory"),
            campaign_id=campaign_id,
            source_table="trades_open",
            source_id=tr.get("id"),
            netcash=0.0,
            proceeds=0.0,
            commission=0.0,
            pnl=0.0,
            quantity=added_qty,
            action='STOCK_SPLIT',
            dateTime=tr.get("dateTime"),
            conid=tr.get("conid"),
            currency=tr.get("currency", "USD"),
            fxRateToBase=tr.get("fxRateToBase", 1)
        )


def process_raw_trade(log, raw_data, repo, tracker, campaign_id):
    # verarbeite eine Raw-Trade (eine Zeile)
    # prüfe gegen OPEN-Tabelle
    new_trade = clean_trade_dict(raw_data)
    raw_trade_id = new_trade['id']
    symbol = new_trade['symbol']
    remaining_qty = new_trade['quantity']  # Die Menge, die wir "abarbeiten" müssen

    # Beim Umstausch werden 2 Trades erzeugt:
    # die quantity gibt die Reihenfolge an 1, bzw. 2
    # -> Eintrag in Ledger und Raw-Trade als processed markieren
    if new_trade['assetCategory'] == 'CASH':
        if remaining_qty == 1 or remaining_qty == 2:
            base, quote = new_trade.get("symbol").split(".")
            if remaining_qty == 1:
                action = f"FX_EXCHANGE_FROM_{base}"
            else:
                action = f"FX_EXCHANGE_TO_{quote}"
            tracker.link_to_campaign_new(
                assetCategory=new_trade.get("assetCategory"),
                campaign_id=campaign_id,
                source_table="trades_raw",
                source_id=raw_trade_id,
                netcash=to_decimal(new_trade['netCash']),
                proceeds=Decimal('0'),
                commission=to_decimal(new_trade['ibCommission']),
                pnl=Decimal(new_trade['tradePrice']),  # der Umrechnungsfaktor
                quantity=Decimal('0'),
                action=action,
                dateTime=new_trade.get("dateTime"),
                conid=new_trade.get("conid"),
                currency=new_trade.get("currency", "USD"),
                fxRateToBase=new_trade.get("fxRateToBase", 1)
            )
        repo.mark_trade_processed(TABLE_TRADES_RAW, raw_trade_id)
        return

    # normale Trades werden ab hier bearbeitet
    # offene Tranchen holen
    open_tranches = repo.get_open_trades(new_trade['assetCategory'], symbol)

    current_inventory = sum(to_decimal(t['quantity']) for t in open_tranches)
    # print_log(log, f"Sym: {symbol} | Anz. OpenTranches: {len(open_tranches)} | Current Inv: {current_inventory} | Raw Qty: {new_trade['quantity']}", True)

    # Prüfen: Gehen wir in die gleiche Richtung? (Zukauf / Short-Vergrößerung)
    is_same_direction = (current_inventory * remaining_qty > 0) or (current_inventory == 0)

    # ==========================================================
    # FALL 1: POSITION VERGRÖSSERN (SAME SIGN)
    # ==========================================================
    if is_same_direction:
        new_trade['status'] = 'OPEN'
        new_id = repo.insert_open_trade(new_trade)
        OpenTradeSchema.log_open_trade(new_trade, "Open", False)

        tracker.link_to_campaign_new(
            assetCategory=new_trade.get("assetCategory"),
            campaign_id=campaign_id,
            source_table="trades_open",
            source_id=new_id,
            netcash=(new_trade.get("netCash") or 0.0),
            proceeds=(new_trade.get("proceeds") or 0.0),
            commission=(new_trade.get('ibCommission') or 0.0),
            pnl=(new_trade.get("profit") or 0.0),
            quantity=new_trade.get("quantity"),
            action='TRADE_OPEN',
            dateTime=new_trade.get("dateTime"),
            conid=new_trade.get("conid"),
            currency=new_trade.get("currency", "USD"),
            fxRateToBase=new_trade.get("fxRateToBase", 1)
        )
        repo.mark_trade_processed(TABLE_TRADES_RAW, raw_trade_id)
        return

    # ==========================================================
    # FALL 2: POSITION VERRINGERN / DREHEN (DIFFERENT SIGNS)
    # ==========================================================
    for tr_raw in open_tranches:
        if remaining_qty == 0:
            break

        tr = clean_trade_dict(tr_raw)
        open_qty = tr['quantity']

        open_abs = abs(open_qty)
        new_abs = abs(remaining_qty)

        # ------------------------------------------------------
        # CASE 2c: EXACT MATCH (Mengen heben sich genau auf)
        # ------------------------------------------------------
        if open_abs == new_abs:
            # realized_pnl = (tr['netCash'] + (new_trade['netCash'] * (new_abs / abs(new_trade['quantity']))))
            ratio = new_abs / abs(new_trade['quantity'])

            cl_trade = OpenTradeSchema.to_closed_trade(tr, new_trade, ratio)
            # print_selected(cl_trade, 'cl_trade',
            #                ["assetCategory", "dateTimeOpen", "dateTimeClose", "quantity", "tradePriceOpen",
            #                 "netCashOpen", "tradePriceClose", "netCashClose", "ibCommission"])

            # input("Drücken Sie die Eingabetaste, um fortzufahren...")

            ClosedTradeSchema.log_closed_trade(cl_trade, "Close", False)
            repo.insert_closed_trade(cl_trade)

            repo.mark_trade_processed(TABLE_TRADES_OPEN, tr['id'])
            netcash = Decimal('0')
            proceeds = Decimal('0')
            commission = Decimal('0')
            if cl_trade["assetCategory"] == "OPT":
                if cl_trade["status"] == "Expired":
                    action = "OPTION_EXPIRATION"
                elif cl_trade["status"] == "Assigned":
                    action = 'OPTION_EXERCISE'
                elif cl_trade["status"] == "CashSettled":
                    action = 'CASH_SETTLEMENT'
                    # das bewegte Cash ist im proceedsClose gespeichert!!
                    # netcash und commission = 0!! (der Code ist Fleißaufgabe)
                    netcash = (cl_trade.get("netCashClose") or 0.0)
                    proceeds = (cl_trade.get("proceedsClose") or 0.0)
                    commission = (cl_trade.get('ibCommission') or 0.0)
                else:
                    action = 'TRADE_CLOSE_FULL'  # Normaler Verkauf vor Ablauf
                    netcash = (cl_trade.get("netCashClose") or 0.0)
                    proceeds = (cl_trade.get("proceedsClose") or 0.0)
                    commission = (cl_trade.get('ibCommission') or 0.0)
            else:
                action = "TRADE_CLOSE_FULL"
                netcash = (cl_trade.get("netCashClose") or 0.0)
                proceeds = (cl_trade.get("proceedsClose") or 0.0)
                commission = (cl_trade.get('ibCommission') or 0.0)

            tracker.link_to_campaign_new(
                assetCategory=cl_trade.get("assetCategory"),
                campaign_id=campaign_id,
                source_table="trades_open",
                source_id=tr['id'],
                netcash=netcash,
                proceeds=proceeds,
                commission=commission,
                pnl=(cl_trade.get("profit") or 0.0),
                quantity=-cl_trade.get("quantity"),
                action=action,
                dateTime=cl_trade.get("dateTimeClose"),
                conid=cl_trade.get("conid"),
                currency=cl_trade.get("currency", "USD"),
                fxRateToBase=cl_trade.get("fxRateToBase_close", 1)
            )

            remaining_qty = Decimal('0')

        # ------------------------------------------------------
        # CASE 2a: PARTIAL CLOSE (Die offene Tranche ist GRÖSSER)
        # ------------------------------------------------------
        elif open_abs > new_abs:
            # Wie viel Prozent der offenen Tranche wird geschlossen?
            close_ratio_of_open = new_abs / open_abs
            # Wie viel Prozent des neuen Trades verbrauchen wir? (Hier 100% des Rests)
            close_ratio_of_new = new_abs / abs(new_trade['quantity'])

            realized_pnl = ((tr['netCash'] * close_ratio_of_open) + (new_trade['netCash'] * close_ratio_of_new))

            # 1. Alte Tranche schließen
            # new_trade muss ich schließen
            cl_trade = OpenTradeSchema.partial_close_new_open(tr, new_trade, close_ratio_of_open)
            # print_selected(cl_trade, 'cl_trade',
            #                ["assetCategory", "dateTimeOpen", "dateTimeClose", "quantity", "tradePriceOpen",
            #                 "netCashOpen", "tradePriceClose", "netCashClose", "ibCommission"])

            ClosedTradeSchema.log_closed_trade(cl_trade, "Close", False)

            # input("Drücken Sie die Eingabetaste, um fortzufahren...")

            # das muss überprüft werden !!
            cl_trade["status"] = "Closed"
            repo.insert_closed_trade(cl_trade)
            repo.mark_trade_processed(TABLE_TRADES_OPEN, tr['id'])

            # 2. Den verbleibenden Rest der alten Tranche neu einbuchen (Split)
            rem_factor = 1 - close_ratio_of_open
            tr['quantity'] = open_qty + remaining_qty
            tr['netCash'] = tr['netCash'] * rem_factor
            tr['proceeds'] = tr['proceeds'] * rem_factor
            tr['ibCommission'] = tr['ibCommission'] * rem_factor
            tr['status'] = 'SPLIT_REST'
            # print_selected(tr, 'tr',
            #                ["assetCategory", "dateTime", "quantity", "tradePrice", "netCash",
            #                 "ibCommission"])
            repo.insert_open_trade(tr)

            # input("Drücken Sie die Eingabetaste, um fortzufahren...")
            OpenTradeSchema.log_open_trade(tr, "Open", False)

            tracker.link_to_campaign_new(
                assetCategory=new_trade.get("assetCategory"),
                campaign_id=campaign_id,
                source_table="trades_open",
                source_id=tr['id'],
                netcash=(new_trade.get("netCash") or 0.0),
                proceeds=(new_trade.get("proceeds") or 0.0),
                commission=(new_trade.get("ibCommission") or 0.0),
                pnl=realized_pnl,
                quantity=new_trade.get("quantity"),
                action='TRADE_CLOSE_PARTIAL',
                dateTime=new_trade.get("dateTime"),
                conid=new_trade.get("conid"),
                currency=new_trade.get("currency", "USD"),
                fxRateToBase=new_trade.get("fxRateToBase", 1)
            )

            remaining_qty = Decimal('0')
        # ------------------------------------------------------
        # CASE 2b: NEW TRADE LARGER (Tranche wird voll geschluckt, Rest bleibt)
        # ------------------------------------------------------
        else:  # new_abs > open_abs
            # Wir verbrauchen 100% der offenen Tranche
            close_ratio_of_new = open_abs / abs(new_trade['quantity'])

            # realized_pnl = -(tr['netCash'] + (new_trade['netCash'] * close_ratio_of_new))

            # 1. Tranche schließen
            cl_trade = OpenTradeSchema.to_closed_trade(tr, new_trade, close_ratio_of_new)
            # print_selected(cl_trade, 'cl_trade',
            #                ["assetCategory", "dateTimeOpen", "dateTimeClose", "quantity", "tradePriceOpen",
            #                 "tradePriceClose", "netCashOpen", "netCashClose", "ibCommission"])

            ClosedTradeSchema.log_closed_trade(cl_trade, "Close", False)
            # das muss überprüft werden !!
            cl_trade["status"] = "Closed"
            repo.insert_closed_trade(cl_trade)

            tracker.link_to_campaign_new(
                assetCategory=cl_trade.get("assetCategory"),
                campaign_id=campaign_id,
                source_table="trades_open",
                source_id=tr['id'],
                netcash=(cl_trade.get("netCashClose") or 0.0),
                proceeds=(cl_trade.get("proceedsClose") or 0.0),
                commission=(cl_trade.get("ibCommission") or 0.0),
                pnl=(cl_trade.get("profit") or 0.0),
                quantity=-cl_trade.get("quantity"),
                action='TRADE_CLOSE_FULL',
                dateTime=cl_trade.get("dateTimeClose"),
                conid=cl_trade.get("conid"),
                currency=cl_trade.get("currency", "USD"),
                fxRateToBase=cl_trade.get("fxRateToBase_close", 1)
            )

            # 2. Den verbleibenden Rest des Tranche berechnen und weitermachen
            rem_factor = 1 - close_ratio_of_new
            new_trade['quantity'] = new_trade['quantity'] + open_qty
            new_trade['netCash'] = new_trade['netCash'] * rem_factor
            new_trade['proceeds'] = new_trade['proceeds'] * rem_factor
            new_trade['ibCommission'] = new_trade['ibCommission'] * rem_factor
            # print_selected(new_trade, 'new_trade',
            #                ["assetCategory", "dateTime", "quantity", "tradePrice", "netCash",
            #                 "ibCommission"])

            # input("Drücken Sie die Eingabetaste, um fortzufahren...")

            repo.mark_trade_processed(TABLE_TRADES_OPEN, tr['id'])

            # 2. Übrig gebliebene Menge des neuen Trades für die nächste Tranche/Reversal merken
            remaining_qty += open_qty

    # --- FINALER CHECK: REVERSAL ---
    # Wenn nach allen offenen Tranchen immer noch Menge übrig ist (Case 2b "Überhang")
    if remaining_qty != 0:
        rev_ratio = abs(remaining_qty / new_trade['quantity'])
        new_trade['quantity'] = remaining_qty
        new_trade['netCash'] = new_trade['netCash'] * rev_ratio
        new_trade['proceeds'] = new_trade['proceeds'] * rev_ratio
        new_trade['ibCommission'] = new_trade['ibCommission'] * rev_ratio
        new_trade['status'] = 'REV_OPEN'
        # print_selected(new_trade, 'new_trade',
        #                ["assetCategory", "dateTime", "quantity", "tradePrice", "netCash",
        #                 "ibCommission"])
        new_id = repo.insert_open_trade(new_trade)
        OpenTradeSchema.log_open_trade(new_trade, "Open", False)

        tracker.link_to_campaign_new(
            assetCategory=new_trade.get("assetCategory"),
            campaign_id=campaign_id,
            source_table="trades_open",
            source_id=new_id,
            netcash=(new_trade.get("netCash") or 0.0),
            proceeds=(new_trade.get("proceeds") or 0.0),
            commission=(new_trade.get("ibCommission") or 0.0),
            pnl=(new_trade.get("profit") or 0.0),
            quantity=new_trade.get("quantity"),
            action='TRADE_REVERSAL_OPEN',
            dateTime=new_trade.get("dateTime"),
            conid=new_trade.get("conid"),
            currency=new_trade.get("currency", "USD"),
            fxRateToBase=new_trade.get("fxRateToBase", 1)
        )

    repo.mark_trade_processed(TABLE_TRADES_RAW, raw_trade_id)


# def _create_new_open_trade(trade: Dict[str, Any], repo, tracker, campaign_id, OpenTradeSchema,
#                            table_trades_raw) -> None:
#     """Erstellt einen neuen Open Trade"""
#     trade['status'] = 'Open'
#
#     OpenTradeSchema.log_open_trade(trade)
#
#     # Unwanted Fields entfernen
#     UNWANTED_FIELDS = {"source", "is_split", "split_type", "actionID"}
#     for field in UNWANTED_FIELDS:
#         trade.pop(field, None)
#
#     source_id = repo.insert_open_trade(trade)
#     repo.mark_trade_processed(table_trades_raw, trade["id"])
#
#     tracker.link_to_campaign(
#         assetCategory=trade.get("assetCategory"),
#         campaign_id=campaign_id,
#         source_table="trades_open",
#         source_id=source_id,
#         netcash=(trade.get("netCash") or 0.0),
#         proceeds=(trade.get("proceeds") or 0.0),
#         pnl=0.0,
#         qty=trade.get("quantity"),
#         action=trade.get("status")  # z.B. 'Trade', 'Assignment', 'Expiration'
#     )
#
#     print_log(logger, f"✅ Neue Position eröffnet: {trade['symbol']}", True)


# def _handle_update_action(trade: Dict[str, Any], open_trade: Dict[str, Any], result: Dict[str, Any], repo, tracker,
#                           campaign_id, OpenTradeSchema) -> None:
#     """Behandelt UPDATE Action - Position aufstocken"""
#     old_qty = abs(open_trade['quantity'])
#     new_qty = abs(trade['quantity'])
#     source_id = int(trade["id"])
#
#     repo.update_open_trade(result)
#     OpenTradeSchema.log_open_trade(result, "OpUp", True)
#
#     tracker.link_to_campaign(
#         assetCategory=result.get("assetCategory"),
#         campaign_id=campaign_id,
#         source_table="trades_open",
#         source_id=source_id,
#         netcash=(result.get("netCash") or 0.0),
#         proceeds=(result.get("proceeds") or 0.0),
#         pnl=(result.get("profit") or 0.0),
#         qty=new_qty,
#         action='Update'
#     )
#
#
# def _handle_split_update_action(result: Dict[str, Any], repo, tracker, campaign_id, OpenTradeSchema) -> None:
#     """Behandelt SPLIT UPDATE Action"""
#     multiplier = result.get('multiplier', 1.0)
#     repo.update_open_trade(result)
#     OpenTradeSchema.log_open_trade(result, "Split")
#     print_log(logger, f"🔄 Split verarbeitet: {result.get('symbol')}")
#
#
# def _handle_close_action(result: Dict[str, Any], open_trade: Dict[str, Any], repo, tracker, campaign_id,
#                          ClosedTradeSchema) -> None:
#     """Behandelt CLOSE Action - Position vollständig schließen"""
#     ClosedTradeSchema.log_closed_trade(result, "Close", False)
#     closed_trade_id = repo.insert_closed_trade(result)
#     tracker.link_to_campaign(
#         assetCategory=result.get("assetCategory"),
#         campaign_id=campaign_id,
#         source_table="trades_closed",
#         source_id=closed_trade_id,
#         netcash=(result.get("netCashClose") or 0.0),  # bei Closed-Trades gibt es kein Feld netCash mehr !!!
#         proceeds=(result.get("proceedsClose") or 0.0),
#         pnl=(result.get("profit") or 0.0),
#         qty=result.get("quantity"),
#         action=result.get("status")  # z.B. 'Trade', 'Assignment', 'Expiration'
#     )
#
#     # Pivot-Tabelle aktualisieren
#     if open_trade.get("tradeID"):
#         repo.update_notes_tag_pivot(open_trade["tradeID"])
#
#     repo.delete_open_trade(open_trade['id'])
#
#     print_log(logger, f"🔒 Position geschlossen: {result.get('symbol')}")
#
#
# def _handle_close_update_action(result: tuple, repo, tracker, campaign_id, OpenTradeSchema, ClosedTradeSchema) -> None:
#     """Behandelt CLOSE_UPDATE Action - Teilweises Schließen, Rest bleibt offen"""
#     closed_trade, updated_open = result
#
#     source_id = repo.insert_closed_trade(closed_trade)
#     ClosedTradeSchema.log_closed_trade(closed_trade, "PartClose", False)
#
#     tracker.link_to_campaign(
#         assetCategory=closed_trade.get("assetCategory"),
#         campaign_id=campaign_id,
#         source_table="trades_closed",
#         source_id=source_id,
#         netcash=(closed_trade.get("netCashClose") or 0.0),  # bei Closed-Trades gibt es kein Feld netCash mehr !!!
#         proceeds=(closed_trade.get("proceedsClose") or 0.0),
#         pnl=(closed_trade.get("profit") or 0.0),
#         qty=closed_trade.get("quantity"),
#         action=closed_trade.get("status")  # z.B. 'Trade', 'Assignment', 'Expiration'
#     )
#
#     if updated_open.get("tradeID"):
#         repo.update_notes_tag_pivot(updated_open["tradeID"])
#
#     source_id = repo.update_open_trade(updated_open)
#     OpenTradeSchema.log_open_trade(updated_open, "RestOpen")
#     tracker.link_to_campaign(
#         assetCategory=updated_open.get("assetCategory"),
#         campaign_id=campaign_id,
#         source_table="trades_open",
#         source_id=source_id,
#         netcash=(updated_open.get("netCash") or 0.0),
#         proceeds=(updated_open.get("proceeds") or 0.0),
#         pnl=(updated_open.get("profit") or 0.0),
#         qty=updated_open.get("quantity"),
#         action='Pcu'  # PCU (Partial Close Update)
#     )
#
#     print_log(logger,
#               f"🔓 Teilweises Schließen: {closed_trade.get('symbol')} - "
#               f"Rest: {updated_open.get('quantity')}"
#               )
#
#
# def _handle_close_new_action(result: tuple, trade: Dict[str, Any], open_trade: Dict[str, Any], repo, tracker,
#                              campaign_id, OpenTradeSchema, ClosedTradeSchema) -> None:
#     """Behandelt CLOSE_NEW Action - Alte Position schließen, neue eröffnen (Oversell)"""
#     closed_trade, new_open = result
#
#     source_id = repo.insert_closed_trade(closed_trade)
#     ClosedTradeSchema.log_closed_trade(closed_trade, "Close", False)
#     tracker.link_to_campaign(
#         assetCategory=closed_trade.get("assetCategory"),
#         campaign_id=campaign_id,
#         source_table="trades_closed",
#         source_id=source_id,
#         netcash=(closed_trade.get("netCash") or 0.0),
#         proceeds=(closed_trade.get("proceeds") or 0.0),
#         pnl=(closed_trade.get("profit") or 0.0),
#         qty=closed_trade.get("quantity"),
#         action=closed_trade.get("status")  # z.B. 'Trade', 'Assignment', 'Expiration'
#     )
#
#     if open_trade.get("tradeID"):
#         repo.update_notes_tag_pivot(open_trade["tradeID"])
#     repo.delete_open_trade(open_trade['id'])
#
#     source_id = repo.insert_open_trade(new_open)
#     OpenTradeSchema.log_open_trade(new_open, "NewOpen")
#
#     tracker.link_to_campaign(
#         assetCategory=new_open.get("assetCategory"),
#         campaign_id=campaign_id,
#         source_table="trades_open",
#         source_id=source_id,
#         netcash=(new_open.get("netCash") or 0.0),
#         proceeds=(new_open.get("proceeds") or 0.0),
#         pnl=0.0,
#         qty=new_open.get("quantity"),
#         action='Rev'  # REV (Reverse) oder RCO (Reverse Close Open)
#     )
#
#     print_log(logger,
#               f"🔄 Oversell: Alte Position geschlossen, neue eröffnet - "
#               f"{new_open.get('symbol')}, Qty: {new_open.get('quantity')}"
#               )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Bitte Environment angeben: money | paper | test | autom_money | autom_paper")
        print("Optional: Table-Prefix, z.B.: python reset_IBKR_DB.py money mike_")
        table_prefix = "mike_"
        env = "test"
        # sys.exit(1)
    elif len(sys.argv) >= 3:
        # --- OPTIONALER TABLE PREFIX ÜBER COMMANDLINE ---
        table_prefix = sys.argv[2]
        print(f"*** TABLE PREFIX via Commandline aktiv: '{table_prefix}' ***")
        env = sys.argv[1].lower()
    else:
        table_prefix = TABLE_PREFIX
        env = sys.argv[1].lower()
    process_trades(env, table_prefix, TABLE_TRADES_RAW)
