# Konfiguration
MAX_GAP_DAYS = 3  # Wie viele Tage darf die Position "flat" sein?


def get_campaign_id(row, last_campaigns_cache):
    symbol = row['symbol']
    trade_date = row['date']

    # 1. Prüfe, ob wir gerade eine aktive Kampagne für das Symbol haben
    if symbol in last_campaigns_cache:
        camp = last_campaigns_cache[symbol]

        # Falls die Kampagne als "geschlossen" markiert war:
        if camp['status'] == 'CLOSED':
            days_since_close = (trade_date - camp['close_date']).days

            if days_since_close <= MAX_GAP_DAYS:
                # RE-OPEN: Gleiche Kampagne weiternutzen
                return camp['id']
            else:
                # NEW: Zu lange her, neue ID generieren
                return create_new_id()
        else:
            # Kampagne ist noch aktiv (Inventory > 0)
            return camp['id']

    return create_new_id()


from datetime import datetime, timedelta


class InventoryTracker:
    def __init__(self, max_gap_days=3):
        # holdings: { 'SYMBOL': { 'shares': 0, 'options': 0, 'campaign_id': ID, 'closed_at': DATE, 'status': 'ACTIVE'|'PENDING' } }
        self.holdings = {}
        self.campaign_counter = 0
        self.max_gap_days = max_gap_days

    def _generate_id(self):
        self.campaign_counter += 1
        return f"CAMP_{self.campaign_counter:05d}"

    def process_transaction(self, row):
        symbol = row['underlying_symbol']
        qty = row['quantity']
        asset_type = row['asset_category']
        trade_date = row['settle_date']  # Sollte ein datetime.date Objekt sein
        trade_type = row['type']

        if symbol not in self.holdings:
            self.holdings[symbol] = {'shares': 0, 'options': 0, 'campaign_id': None, 'closed_at': None, 'status': None}

        h = self.holdings[symbol]

        # --- LOOKBACK LOGIK: Prüfen auf Reaktivierung ---
        if qty != 0:
            if h['campaign_id'] is not None and h['status'] == 'PENDING':
                days_passed = (trade_date - h['closed_at']).days

                if days_passed <= self.max_gap_days:
                    # Reaktivieren: Wir setzen das Wochenende/die Pause einfach fort
                    h['status'] = 'ACTIVE'
                    h['closed_at'] = None
                    print(
                        f"[RE-OPEN] {symbol}: Alte Kampagne {h['campaign_id']} wird fortgesetzt ({days_passed} Tage Lücke).")
                else:
                    # Zu lange her: Neue Kampagne starten
                    h['campaign_id'] = self._generate_id()
                    h['status'] = 'ACTIVE'
                    h['closed_at'] = None
                    print(f"[NEW] {symbol}: Neue Kampagne {h['campaign_id']} gestartet (Lücke war zu groß).")

            elif h['campaign_id'] is None:
                # Ganz neuer Start
                h['campaign_id'] = self._generate_id()
                h['status'] = 'ACTIVE'

        # --- INVENTORY UPDATE ---
        if asset_type == 'STK':
            h['shares'] += qty
        elif asset_type == 'OPT':
            if trade_type == 'Expiration':
                h['options'] = 0
            else:
                h['options'] += qty

        # --- STATUS-CHECK: Flat gehen ---
        is_flat = (h['shares'] == 0 and h['options'] == 0)
        current_id = h['campaign_id']

        if is_flat and h['status'] == 'ACTIVE':
            # Nicht sofort löschen, sondern in den Wartezustand versetzen
            h['status'] = 'PENDING'
            h['closed_at'] = trade_date
            print(f"[PENDING] {symbol}: Bestand ist 0. Warte {self.max_gap_days} Tage auf neue Trades...")

        return current_id

def link_to_campaign(db_conn, campaign_id, source_table, source_id, pnl=0.0, qty=0, action='Trade'):
    """
    Verknüpft eine Transaktion (Open oder Close) mit einer Kampagne im Ledger.
    """
    cursor = db_conn.cursor()

    # 1. Eintrag in den Ledger schreiben
    sql_ledger = """
        INSERT INTO campaign_ledger 
        (campaign_id, source_table, source_id, pnl_impact, inventory_delta, action)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    cursor.execute(sql_ledger, (campaign_id, source_table, source_id, pnl, qty, action))

    # 2. Zeitstempel in der Hauptkampagne aktualisieren
    sql_update_campaign = """
        UPDATE trading_campaigns 
        SET end_date = NOW() 
        WHERE id = %s
    """
    cursor.execute(sql_update_campaign, (campaign_id,))

    db_conn.commit()





# Beispielhafte Integration in deine 4 Punkte:

def process_your_trades(row, campaign_id, db_conn):
    # ... Deine Logik für Open/Close ...

    if action == "ASSIGNED":
        # 1. Die Option wird geschlossen
        close_id = move_to_closed_table(row)  # deine Funktion
        link_to_campaign(db_conn, campaign_id, 'closed_trades', close_id, pnl=row['premium'], qty=0,
                         action='Assignment-Close')

        # 2. Die Aktie wird eingebucht
        open_id = write_to_open_table(row)  # deine Funktion
        link_to_campaign(db_conn, campaign_id, 'open_trades', open_id, pnl=0, qty=100, action='Assignment-Stock-Open')

    elif action == "EXPIRED":
        close_id = move_to_closed_table(row)
        link_to_campaign(db_conn, campaign_id, 'closed_trades', close_id, pnl=row['premium'], qty=0,
                         action='Expiration')

    elif action == "CLOSE":
        close_id = move_to_closed_table(row)
        link_to_campaign(db_conn, campaign_id, 'closed_trades', close_id, pnl=calculated_pnl, qty=row['qty'],
                         action='Trade-Close')

