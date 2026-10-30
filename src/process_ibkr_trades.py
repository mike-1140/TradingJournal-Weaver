import sys
import uuid
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any

import pandas as pd

from src.config import TABLE_PREFIX, TABLE_TRADES_RAW, TABLE_TRADES_OPEN, load_active_targets
from src.db.db_access import DBAccess, TradeRepository
from src.logger_setup import setup_logging, print_log
from src.parsers.inventory_tracker import InventoryTracker
from src.trade_schemas import OpenTradeSchema, ClosedTradeSchema
from src.utils.div_utils import to_decimal
from src.utils.path_utils import get_project_root
from src.trade_enums import AssetCategory, BuySell, CampaignStatus, LedgerAction, TradeStatus
from src.utils.progress import ProgressLine

# Logging
log_file = get_project_root() / "log/app.log"
logger, _ = setup_logging('my_app', level="simple", log_file=log_file)
INPUT_DIR = get_project_root() / "input"


def apply_split(old_split, new_split):

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


def _open_action(asset: str, put_call, buy_sell: str) -> LedgerAction:
    """Bestimmt die feingranulare Ledger-Action beim Eröffnen einer Position."""
    if asset == AssetCategory.OPTION:
        is_put = str(put_call) == 'P'
        is_buy = buy_sell == BuySell.BUY
        if is_put:
            return LedgerAction.OPT_PUT_BUY if is_buy else LedgerAction.OPT_PUT_SELL
        else:
            return LedgerAction.OPT_CALL_BUY if is_buy else LedgerAction.OPT_CALL_SELL
    return LedgerAction.STK_BUY if buy_sell == BuySell.BUY else LedgerAction.STK_SELL


def _close_action(asset: str, put_call, buy_sell: str, partial: bool = False) -> LedgerAction:
    """Bestimmt die feingranulare Ledger-Action beim Schließen einer Position."""
    if asset == AssetCategory.OPTION:
        is_put = str(put_call) == 'P'
        is_buy = buy_sell == BuySell.BUY
        if is_put:
            if is_buy:
                return LedgerAction.OPT_PUT_BUY_PARTIAL if partial else LedgerAction.OPT_PUT_BUY_CLOSE
            return LedgerAction.OPT_PUT_SELL_PARTIAL if partial else LedgerAction.OPT_PUT_SELL_CLOSE
        else:
            if is_buy:
                return LedgerAction.OPT_CALL_BUY_PARTIAL if partial else LedgerAction.OPT_CALL_BUY_CLOSE
            return LedgerAction.OPT_CALL_SELL_PARTIAL if partial else LedgerAction.OPT_CALL_SELL_CLOSE
    if buy_sell == BuySell.SELL:
        return LedgerAction.STK_SELL_PARTIAL if partial else LedgerAction.STK_SELL_CLOSE
    return LedgerAction.STK_BUY_PARTIAL if partial else LedgerAction.STK_BUY_CLOSE


def _close_booking(cl_trade, new_trade, tracker, close_commission, partial: bool = False):
    """
    Ledger-Buchung beim Schließen einer Tranche (Fälle 2a/2b/2c gemeinsam).
    Optionen werten den Status des schließenden Events aus (Verfall/Zuteilung/Barausgleich) —
    auch wenn nur ein Teil der Tranche oder mehrere Tranchen geschlossen werden.
    Rückgabe: (action, netcash, proceeds, commission, link_id)
    """
    action = _close_action(cl_trade.get("assetCategory"), cl_trade.get("putCall"),
                           cl_trade.get("buySellClose"), partial=partial)
    netcash = to_decimal(cl_trade.get("netCashClose"))
    proceeds = to_decimal(cl_trade.get("proceedsClose"))
    commission = close_commission
    link_id = cl_trade.get("linkID")

    if cl_trade["assetCategory"] == AssetCategory.OPTION:
        status = cl_trade.get("status")
        if status == TradeStatus.EXPIRED:
            action = LedgerAction.OPTION_EXPIRATION
            netcash = proceeds = commission = Decimal('0')
        elif status == TradeStatus.ASSIGNED:
            action = LedgerAction.OPTION_EXERCISE
            netcash = proceeds = commission = Decimal('0')
            # linkID im Tracker merken, damit der folgende STK-Open (aus dem Assignment)
            # denselben linkID bekommt
            link_id = link_id or str(uuid.uuid4())
            underlying = cl_trade.get("underlyingSymbol") or cl_trade.get("symbol")
            if underlying in tracker.holdings:
                tracker.holdings[underlying]['pending_link_id'] = link_id
                tracker.holdings[underlying]['pending_link_time'] = new_trade.get("dateTime")
        elif status == TradeStatus.CASH_SETTLED:
            # das bewegte Cash steht in netCashClose/proceedsClose (BookTrade, Kommission 0)
            action = LedgerAction.CASH_SETTLEMENT

    return action, netcash, proceeds, commission, link_id


OPTION_EVENT_STATUSES = (TradeStatus.EXPIRED, TradeStatus.ASSIGNED, TradeStatus.CASH_SETTLED)
IGNORE_ORDER_FLAG = "--reihenfolge-ignorieren"


def find_out_of_order_trades(df_raw, last_processed_dt):
    """
    Unverarbeitete Trades, die zeitlich VOR dem jüngsten bereits verarbeiteten liegen
    (z. B. alte Berichte nachgeholt). Sie würden gegen den aktuellen Stand laufen —
    etwa ein Verkauf ohne Bestand, der eine falsche Short-Tranche eröffnet.
    Rückgabe: (blockierend, toleriert) als DataFrames.
      - toleriert: Options-Ereignisse (Verfall/Zuteilung/Barausgleich) — IBKR liefert sie
        gelegentlich erst mit dem Bericht des Folgetags; die Options-Tranche existiert ja.
      - CASH wird nie geprüft (kein FIFO).
    """
    empty = df_raw.iloc[0:0]
    if last_processed_dt is None or df_raw.empty:
        return empty, empty
    earlier = df_raw[(df_raw['assetCategory'] != AssetCategory.CASH)
                     & (pd.to_datetime(df_raw['dateTime']) < pd.Timestamp(last_processed_dt))]
    is_option_event = (earlier['assetCategory'] == AssetCategory.OPTION) & \
                      earlier['status'].isin([s.value for s in OPTION_EVENT_STATUSES])
    return earlier[~is_option_event], earlier[is_option_event]


def process_trades(environment: str, table_pref: str, table_trades_raw, ignore_order: bool = False) -> bool:
    """
    Verarbeitet Trades aus der RAW-Tabelle und aktualisiert Open/Closed Trades

    Args:
        environment: Trading Environment ('money', 'paper', 'test')
        table_pref: Tabellen-Prefix für Multi-User Support
        table_trades_raw:
        ignore_order: Verarbeiten, auch wenn Trades in falscher Reihenfolge vorliegen
    Returns:
        False, wenn die Verarbeitung wegen falscher Reihenfolge angehalten wurde, sonst True
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

    # ===== DATEN LADEN =====
    # Zuerst laden, damit der erste Trade-Zeitpunkt an den Tracker übergeben werden kann.
    # close_old_pending_campaigns() darf nicht mit datetime.now() laufen, sonst werden
    # Kampagnen zu früh geschlossen, wenn Trades mit Verzögerung importiert werden.
    df_raw = db.get_all_raw_trades(env_up, table_trades_raw)

    if df_raw.empty:
        print_log(logger, "Keine neuen Trades zum Verarbeiten gefunden", True)
        return True

    # ===== REIHENFOLGE PRÜFEN =====
    last_processed_dt = db.get_last_processed_raw_datetime(env_up, table_trades_raw)
    blocking, tolerated = find_out_of_order_trades(df_raw, last_processed_dt)
    if not tolerated.empty:
        logger.info(f"Hinweis: {len(tolerated)} Options-Ereignis(se) (Verfall/Zuteilung/Barausgleich) "
                    f"liegen vor dem zuletzt verarbeiteten Trade ({last_processed_dt}) — unkritisch, "
                    f"werden verarbeitet")
    if not blocking.empty:
        first = blocking.iloc[0]
        msg = (f"{env_up}: {len(blocking)} neue(r) Trade(s) liegen zeitlich VOR dem zuletzt verarbeiteten "
               f"Trade ({last_processed_dt}), ältester: {first['dateTime']} {first['symbol']}. "
               f"Verarbeitung gegen den aktuellen Stand kann falsche Positionen erzeugen "
               f"(z. B. Verkauf ohne Bestand).")
        if ignore_order:
            logger.warning(msg + f" Wird wegen {IGNORE_ORDER_FLAG} trotzdem verarbeitet.")
        else:
            logger.error(msg)
            logger.error(f"{env_up} wird NICHT verarbeitet. Empfohlen: Environment neu aufbauen "
                         f"(reset_IBKR_DB.py + Import mit --from-summary). Bewusst trotzdem verarbeiten: "
                         f"python -m src.process_ibkr_trades {environment} {table_pref} {IGNORE_ORDER_FLAG}")
            return False

    first_trade_date = df_raw.iloc[0]['dateTime']
    tracker = InventoryTracker(logger, db, table_pref,
                               env_up, reference_date=first_trade_date)

    total = len(df_raw)
    logger.info(f"{total} Trades zum Bearbeiten gefunden")

    # ===== SPLIT-HANDLING VORBEREITUNG =====
    split_buffer = defaultdict(list)

    # ===== HAUPTSCHLEIFE =====
    progress = ProgressLine(logger)
    progress.start()
    last_trade_date = None

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

        last_trade_date = row['dateTime']

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
                split_symbol = _resolve_split_holdings_symbol(trade)
                campaign_id = (tracker.holdings.get(split_symbol) or {}).get('campaign_id')
                process_stock_split(repo, trade, tracker, campaign_id)
                # In-memory Bestand an neuen Faktor anpassen
                if split_symbol in tracker.holdings:
                    factor = to_decimal(trade.get('multiplier', 1))
                    h = tracker.holdings[split_symbol]
                    h['shares'] = to_decimal(h['shares']) * factor

                    # Flat-Check nach Split — konsistent mit dem normalen PENDING-Mechanismus
                    tracker.recheck_flat_status(h['campaign_id'], split_symbol, trade.get('dateTime'))
            continue  # Split vollständig verarbeitet oder wartet auf zweiten Teil

        # Jeder Raw-Trade wird atomar verarbeitet: alle DB-Operationen (Kampagne,
        # Ledger, Open/Close, processed-Flag) werden gemeinsam committed oder
        # bei Exception komplett zurückgerollt.
        with db.transaction():
            # CASH-Trades gehören zu keiner Kampagne — keinen Inventory-Tracker aufrufen
            if trade.get('assetCategory') == AssetCategory.CASH:
                campaign_id = None
            else:
                campaign_id = tracker.process_row_and_get_campaign(row)

            # ===== SCHRITT 5: TRADE VERARBEITUNG =====
            process_raw_trade(logger, trade, repo, tracker, campaign_id)

            # Flat-Check nach Verarbeitung (trades_open als Wahrheitsquelle — Fix A)
            if campaign_id:
                recheck_symbol = row.get('underlyingSymbol') or row.get('symbol')
                tracker.recheck_flat_status(campaign_id, recheck_symbol, row.get('dateTime'))

    progress.done(f"{total} Trades verarbeitet  [{env_up}]")

    # Letztes Trade-Datum für Kampagnen-Cleanup verwenden (nicht das aktuelle Systemdatum)
    tracker.finalize(last_trade_date or datetime.now())

    logger.info("=" * 80)
    logger.info("Trade-Verarbeitung abgeschlossen")
    logger.info("=" * 80)
    return True


def _resolve_split_holdings_symbol(trade: Dict[str, Any]) -> str:
    """
    Ermittelt das Symbol, unter dem ein verarbeiteter Split-Trade im
    tracker.holdings-Dict nachgeschlagen werden muss.

    Nach _handle_split_trade() ist trade['symbol'] bereits auf das NEUE
    Symbol nach dem Split gesetzt; trade['underlyingSymbol'] zeigt beim alten
    Split-Leg dagegen oft noch auf das ALTE Symbol (z.B. "APDN.OLD").

    Regressions-Bug (behoben 2026-05-11): eine frühere Fassung löste hier
    'underlyingSymbol or symbol' auf und griff dadurch ins Leere — die
    Kampagne wurde im Tracker nie gefunden, der In-Memory-Bestand nie
    aktualisiert, die Kampagne blieb fälschlich ACTIVE obwohl der Bestand
    nach dem Split rechnerisch 0 war.
    """
    return trade.get('symbol')


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
        repo.mark_trade_processed(table_trades_raw, trade["id"])
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

    # Fallback: campaign_id aus DB laden, wenn tracker.holdings es nicht kennt
    if campaign_id is None and open_tranches:
        campaign_id = repo.get_active_campaign_id_by_symbol(trade['symbol'])
        if campaign_id is None:
            logger.warning(
                f"Split-Verarbeitung: Keine aktive Kampagne für {trade['symbol']} gefunden "
                f"— Tranche(n) werden aktualisiert, aber kein Ledger-Eintrag."
            )

    for tr in open_tranches:
        old_qty = to_decimal(tr['quantity'])
        new_qty = old_qty * to_decimal(factor)
        new_price = to_decimal(tr["tradePrice"] / factor)
        added_qty = new_qty - old_qty  # Das ist das Delta für den Ledger

        # 2. Tranche in trades_open aktualisieren
        if new_qty == 0:
            # Position vollständig eliminiert (z.B. Reverse Split mit 0 ganzen Aktien)
            # Tranche als abgeschlossen markieren — quantity=0 würde FIFO-Loop verwirren
            repo.mark_trade_processed(TABLE_TRADES_OPEN, tr["id"])
        else:
            repo.update_open_trade({
                "id": tr["id"],
                "quantity": new_qty,
                "tradePrice": new_price
            })
        # 3. Ledger informieren (Nur Bestandsänderung, kein Cash!)
        if campaign_id is None:
            continue  # Kein Ledger-Eintrag ohne gültige Kampagne
        tracker.link_to_campaign_new(
            assetCategory=tr.get("assetCategory"),
            campaign_id=campaign_id,
            source_table="TRADES_OPEN",
            source_id=tr.get("id"),
            netcash=0.0,
            proceeds=0.0,
            commission=0.0,
            pnl=0.0,
            quantity=added_qty,
            action=LedgerAction.STOCK_SPLIT,
            dateTime=trade.get("dateTime"),
            conid=tr.get("conid"),
            currency=tr.get("currency", "USD"),
            fxRateToBase=tr.get("fxRateToBase", 1),
            symbol=tr.get("symbol"),
            trade_price=tr.get("tradePrice"),
            multiplier=tr.get("multiplier")
        )


def process_raw_trade(log, raw_data, repo, tracker, campaign_id):
    # verarbeite eine Raw-Trade (eine Zeile)
    # prüfe gegen OPEN-Tabelle
    new_trade = clean_trade_dict(raw_data)
    raw_trade_id = new_trade['id']
    symbol = new_trade['symbol']
    remaining_qty = new_trade['quantity']  # Die Menge, die wir "abarbeiten" müssen

    if not new_trade.get('dateTime'):
        log.warning(f"dateTime fehlt für Trade ID {raw_trade_id} ({symbol}) — Trade übersprungen")
        return

    # Devisentausch (CASH): kein FIFO, keine Kampagne, kein Ledger-Eintrag — die Tausche stehen
    # bereits seit dem Import in trades_fx. Raw-Trade nur als verarbeitet markieren.
    if new_trade['assetCategory'] == AssetCategory.CASH:
        repo.mark_trade_processed(TABLE_TRADES_RAW, raw_trade_id)
        return

    # normale Trades werden ab hier bearbeitet
    # offene Tranchen holen
    open_tranches = repo.get_open_trades(new_trade['assetCategory'], symbol, conid=new_trade.get('conid'))

    current_inventory = sum(to_decimal(t['quantity']) for t in open_tranches)

    # Prüfen: Gehen wir in die gleiche Richtung? (Zukauf / Short-Vergrößerung)
    is_same_direction = (current_inventory * remaining_qty > 0) or (current_inventory == 0)

    # ==========================================================
    # FALL 1: POSITION VERGRÖSSERN (SAME SIGN)
    # ==========================================================
    if is_same_direction:
        new_trade['status'] = TradeStatus.OPEN
        new_id = repo.insert_open_trade(new_trade)
        OpenTradeSchema.log_open_trade(new_trade, "Open", False)

        # Assignment-linkID konsumieren (falls dieser STK-Open durch ein Assignment ausgelöst wurde).
        # Nur gültig für dieselbe Zuteilung (gleicher Zeitpunkt): wurde der STK-Open vor dem
        # Options-Close verarbeitet, bliebe die gemerkte ID sonst liegen und landete beim
        # nächsten STK-Open des Symbols. Eine eigene linkID aus trades_raw hat immer Vorrang.
        h_open = tracker.holdings.get(symbol, {})
        pending_link_id = h_open.pop('pending_link_id', None) if h_open else None
        pending_link_time = h_open.pop('pending_link_time', None) if h_open else None
        if pending_link_id and str(pending_link_time) != str(new_trade.get("dateTime")):
            pending_link_id = None

        tracker.link_to_campaign_new(
            assetCategory=new_trade.get("assetCategory"),
            campaign_id=campaign_id,
            source_table="TRADES_OPEN",
            source_id=new_id,
            netcash=to_decimal(new_trade.get("netCash")),
            proceeds=to_decimal(new_trade.get("proceeds")),
            commission=to_decimal(new_trade.get('ibCommission')),
            pnl=to_decimal(new_trade.get("profit")),
            quantity=new_trade.get("quantity"),
            action=_open_action(new_trade.get("assetCategory"), new_trade.get("putCall"), new_trade.get("buySell")),
            dateTime=new_trade.get("dateTime"),
            conid=new_trade.get("conid"),
            currency=new_trade.get("currency", "USD"),
            fxRateToBase=new_trade.get("fxRateToBase", 1),
            symbol=new_trade.get("symbol"),
            trade_price=new_trade.get("tradePrice"),
            strike=new_trade.get("strike"),
            expiry=new_trade.get("expiry"),
            multiplier=new_trade.get("multiplier"),
            put_call=new_trade.get("putCall"),
            buy_sell=new_trade.get("buySell"),
            link_id=new_trade.get("linkID") or pending_link_id
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
            ratio = new_abs / abs(new_trade['quantity'])
            # Nur die Schließ-Kommission ans Ledger — Opening-Kommission wurde beim TRADE_OPEN bereits gebucht
            close_commission_2c = to_decimal(new_trade.get('ibCommission')) * to_decimal(ratio)

            cl_trade = OpenTradeSchema.to_closed_trade(tr, new_trade, ratio)


            ClosedTradeSchema.log_closed_trade(cl_trade, "Close", False)
            repo.insert_closed_trade(cl_trade)

            repo.mark_trade_processed(TABLE_TRADES_OPEN, tr['id'])
            action, netcash, proceeds, commission, link_id_2c = _close_booking(
                cl_trade, new_trade, tracker, close_commission_2c)

            tracker.link_to_campaign_new(
                assetCategory=cl_trade.get("assetCategory"),
                campaign_id=campaign_id,
                source_table="TRADES_OPEN",
                source_id=tr['id'],
                netcash=netcash,
                proceeds=proceeds,
                commission=commission,
                pnl=to_decimal(cl_trade.get("profit")),
                quantity=-cl_trade.get("quantity"),
                action=action,
                dateTime=cl_trade.get("dateTimeClose"),
                conid=cl_trade.get("conid"),
                currency=cl_trade.get("currency", "USD"),
                fxRateToBase=cl_trade.get("fxRateToBase_close", 1),
                symbol=cl_trade.get("symbol"),
                trade_price=cl_trade.get("tradePriceClose"),
                strike=cl_trade.get("strike"),
                expiry=cl_trade.get("expiry"),
                multiplier=cl_trade.get("multiplier"),
                put_call=cl_trade.get("putCall"),
                buy_sell=cl_trade.get("buySellClose"),
                link_id=link_id_2c
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

            # P&L: cl_trade['profit'] (= fifoPnlRealized) wird direkt übergeben (konsistent mit Case 2c)

            # 1. Alte Tranche schließen
            # new_trade muss ich schließen
            cl_trade = OpenTradeSchema.partial_close_new_open(tr, new_trade, close_ratio_of_open)

            ClosedTradeSchema.log_closed_trade(cl_trade, "Close", False)

            # Status des schließenden Events (Closed/Expired/Assigned/CashSettled) bleibt erhalten
            repo.insert_closed_trade(cl_trade)
            repo.mark_trade_processed(TABLE_TRADES_OPEN, tr['id'])

            # 2. Den verbleibenden Rest der alten Tranche neu einbuchen (Split)
            rem_factor = 1 - close_ratio_of_open
            tr['quantity'] = open_qty + remaining_qty
            tr['netCash'] = tr['netCash'] * rem_factor
            tr['proceeds'] = tr['proceeds'] * rem_factor
            tr['ibCommission'] = tr['ibCommission'] * rem_factor
            tr['status'] = TradeStatus.SPLIT_REST
            repo.insert_open_trade(tr)

            OpenTradeSchema.log_open_trade(tr, "Open", False)

            # Nur die Schließ-Kommission (new_trade) — Opening-Kommission bereits beim TRADE_OPEN gebucht
            close_commission_2a = to_decimal(new_trade.get('ibCommission'))
            action_2a, netcash_2a, proceeds_2a, commission_2a, link_id_2a = _close_booking(
                cl_trade, new_trade, tracker, close_commission_2a, partial=True)

            tracker.link_to_campaign_new(
                assetCategory=cl_trade.get("assetCategory"),
                campaign_id=campaign_id,
                source_table="TRADES_OPEN",
                source_id=tr['id'],
                netcash=netcash_2a,
                proceeds=proceeds_2a,
                commission=commission_2a,
                pnl=to_decimal(cl_trade.get('profit')),
                quantity=new_trade.get("quantity"),
                action=action_2a,
                dateTime=cl_trade.get("dateTimeClose"),
                conid=cl_trade.get("conid"),
                currency=new_trade.get("currency", "USD"),
                fxRateToBase=new_trade.get("fxRateToBase", 1),
                symbol=cl_trade.get("symbol"),
                trade_price=cl_trade.get("tradePriceClose"),
                strike=cl_trade.get("strike"),
                expiry=cl_trade.get("expiry"),
                multiplier=cl_trade.get("multiplier"),
                put_call=cl_trade.get("putCall"),
                buy_sell=cl_trade.get("buySellClose"),
                link_id=link_id_2a
            )

            remaining_qty = Decimal('0')
        # ------------------------------------------------------
        # CASE 2b: NEW TRADE LARGER (Tranche wird voll geschluckt, Rest bleibt)
        # ------------------------------------------------------
        else:  # new_abs > open_abs
            # Wir verbrauchen 100% der offenen Tranche
            close_ratio_of_new = open_abs / abs(new_trade['quantity'])
            # Nur die anteilige Schließ-Kommission — Opening-Kommission bereits beim TRADE_OPEN gebucht
            close_commission_2b = to_decimal(new_trade.get('ibCommission')) * to_decimal(close_ratio_of_new)


            # 1. Tranche schließen
            cl_trade = OpenTradeSchema.to_closed_trade(tr, new_trade, close_ratio_of_new)

            ClosedTradeSchema.log_closed_trade(cl_trade, "Close", False)
            # Status des schließenden Events (Closed/Expired/Assigned/CashSettled) bleibt erhalten
            repo.insert_closed_trade(cl_trade)
            action_2b, netcash_2b, proceeds_2b, commission_2b, link_id_2b = _close_booking(
                cl_trade, new_trade, tracker, close_commission_2b)

            tracker.link_to_campaign_new(
                assetCategory=cl_trade.get("assetCategory"),
                campaign_id=campaign_id,
                source_table="TRADES_OPEN",
                source_id=tr['id'],
                netcash=netcash_2b,
                proceeds=proceeds_2b,
                commission=commission_2b,
                pnl=to_decimal(cl_trade.get("profit")),
                quantity=-cl_trade.get("quantity"),
                action=action_2b,
                dateTime=cl_trade.get("dateTimeClose"),
                conid=cl_trade.get("conid"),
                currency=cl_trade.get("currency", "USD"),
                fxRateToBase=cl_trade.get("fxRateToBase_close", 1),
                symbol=cl_trade.get("symbol"),
                trade_price=cl_trade.get("tradePriceClose"),
                strike=cl_trade.get("strike"),
                expiry=cl_trade.get("expiry"),
                multiplier=cl_trade.get("multiplier"),
                put_call=cl_trade.get("putCall"),
                buy_sell=cl_trade.get("buySellClose"),
                link_id=link_id_2b
            )

            # 2. Den verbleibenden Rest des Tranche berechnen und weitermachen
            rem_factor = 1 - close_ratio_of_new
            new_trade['quantity'] = new_trade['quantity'] + open_qty
            new_trade['netCash'] = new_trade['netCash'] * rem_factor
            new_trade['proceeds'] = new_trade['proceeds'] * rem_factor
            new_trade['ibCommission'] = new_trade['ibCommission'] * rem_factor


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
        new_trade['status'] = TradeStatus.REV_OPEN
        new_id = repo.insert_open_trade(new_trade)
        OpenTradeSchema.log_open_trade(new_trade, "Open", False)

        tracker.link_to_campaign_new(
            assetCategory=new_trade.get("assetCategory"),
            campaign_id=campaign_id,
            source_table="TRADES_OPEN",
            source_id=new_id,
            netcash=to_decimal(new_trade.get("netCash")),
            proceeds=to_decimal(new_trade.get("proceeds")),
            commission=to_decimal(new_trade.get("ibCommission")),
            pnl=to_decimal(new_trade.get("profit")),
            quantity=new_trade.get("quantity"),
            action=LedgerAction.TRADE_REVERSAL_OPEN,
            dateTime=new_trade.get("dateTime"),
            conid=new_trade.get("conid"),
            currency=new_trade.get("currency", "USD"),
            fxRateToBase=new_trade.get("fxRateToBase", 1),
            symbol=new_trade.get("symbol"),
            trade_price=new_trade.get("tradePrice"),
            strike=new_trade.get("strike"),
            expiry=new_trade.get("expiry"),
            multiplier=new_trade.get("multiplier"),
            put_call=new_trade.get("putCall"),
            buy_sell=new_trade.get("buySell"),
            link_id=new_trade.get("linkID")
        )

    repo.mark_trade_processed(TABLE_TRADES_RAW, raw_trade_id)


if __name__ == "__main__":
    ignore_order = IGNORE_ORDER_FLAG in sys.argv[1:]
    args = [a for a in sys.argv[1:] if a != IGNORE_ORDER_FLAG]
    results = []
    if args:
        # CLI-Override: explizites Environment hat Vorrang vor pipeline.toml
        env          = args[0].lower()
        table_prefix = args[1] if len(args) >= 2 else TABLE_PREFIX
        logger.info(f"CLI-Modus: {env} / {table_prefix}")
        results.append(process_trades(env, table_prefix, TABLE_TRADES_RAW, ignore_order))
    else:
        # Auto-Modus: alle aktiven Targets aus pipeline.toml
        targets = load_active_targets()
        if not targets:
            print("Keine aktiven Targets in pipeline.toml gefunden.")
            sys.exit(0)
        for t in targets:
            results.append(process_trades(t["environment"], t["prefix"], TABLE_TRADES_RAW, ignore_order))
    # Exit-Code 1, wenn ein Environment wegen falscher Reihenfolge angehalten wurde —
    # run_pipeline.py meldet den Schritt dann als FEHLER
    if False in results:
        sys.exit(1)
