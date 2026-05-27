from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import text
from src.config import TABLE_PREFIX, TABLE_CAMPAIGN_LEDGER, TABLE_TRADING_CAMPAIGNS, MAX_GAP_DAYS
from src.utils.div_utils import to_decimal
from src.trade_enums import AssetCategory, CampaignStatus


class InventoryTracker:
    def __init__(self, logger, db_conn, table_prefix, env="TEST", max_gap_days=MAX_GAP_DAYS, reference_date=None):
        self.db_conn = db_conn
        self.table_prefix = table_prefix or TABLE_PREFIX
        self.max_gap_days = max_gap_days
        self.db_logger = logger
        self.env = env

        # schließe abgelaufene Kampagnen — reference_date ist der erste zu verarbeitende Trade-Zeitpunkt,
        # NICHT datetime.now(), da Trades mit Verzögerung importiert werden können (AUTOM-Pipeline).
        self.close_old_pending_campaigns(reference_date=reference_date)
        # Lade laufende Kampagnen aus der DB
        self.holdings = self._load_active_campaigns_from_db()

    def _prefixed(self, table_name: str) -> str:
        """
        Gibt den Tabellennamen mit Präfix zurück.
        """
        if self.table_prefix:
            return f"{self.table_prefix}{table_name}"
        return table_name

    def finalize(self, last_processed_date):
        """
        Wird nach Abschluss aller Trades aufgerufen,
        um die letzten PENDING Kampagnen zu archivieren.
        """
        self.db_logger.info("Starte finalen Cleanup der Kampagnen ... ")
        self._cleanup_expired_campaigns(last_processed_date)

    @staticmethod
    def _determine_strategy(asset_type, qty):
        """Bestimmt die Strategie basierend auf dem Eröffnungs-Trade."""
        if asset_type == AssetCategory.OPTION:
            if qty < 0:
                return 'BONUS/CASHFLOW'  # Short Put/Call
            return 'HEDGE/SPECULATION'  # Long Put/Call
        elif asset_type == AssetCategory.STOCK:
            return 'DIRECT_INVEST'  # Klassischer Aktienkauf
        return 'OTHER'

    def _load_active_campaigns_from_db(self):
        full_table_name = self._prefixed(TABLE_TRADING_CAMPAIGNS)
        # Wir holen alle Kampagnen, die noch nicht final CLOSED sind
        sql = f"""
            SELECT id, symbol, status, end_date 
            FROM {full_table_name}
            WHERE status IN ('ACTIVE', 'PENDING')
        """
        param_dict = {}
        active_ca = self.db_conn.fetch_all(sql, param_dict)

        active_camps = {}

        for row in active_ca:
            # Jetzt berechnen wir den aktuellen Bestand für diese Kampagne aus dem Ledger
            # (Summe aller inventory_deltas im Ledger für diese campaign_id)
            inventory = self._get_current_inventory(int(row['id']))

            active_camps[row['symbol']] = {
                # 'assetCategory': inventory['assetCategory'],
                'campaign_id': row['id'],
                'shares': inventory['shares'],
                'options': inventory['options'],
                'status': row['status'],
                'closed_at': row['end_date'],
                'pending_link_id': None
            }
        return active_camps

    def _get_current_inventory(self, campaign_id):
        # cursor = self.db_conn.cursor(dictionary=True)
        full_table_name = self._prefixed(TABLE_CAMPAIGN_LEDGER)
        sql = f"""
            SELECT 
                SUM(CASE WHEN assetCategory = 'STK' THEN inventory_delta ELSE 0 END) as shares,
                SUM(CASE WHEN assetCategory = 'OPT' THEN inventory_delta ELSE 0 END) as options
            FROM {full_table_name}
            WHERE campaign_id = :id
        """
        param_dict = {"id": campaign_id}
        result = self.db_conn.fetch_one(sql, param_dict)

        # Falls die Kampagne brandneu ist, liefert SQL NULL, das fangen wir ab:
        return {
            'shares': to_decimal(result['shares'] or 0),
            'options': to_decimal(result['options'] or 0)
        }

    def _cleanup_expired_campaigns(self, current_trade_date):
        """
        Prüft alle PENDING Kampagnen im Speicher. Wenn die Gap-Tage
        überschritten sind, werden sie in der DB auf CLOSED gesetzt.
        """
        for symbol, h in list(self.holdings.items()):
            if h['status'] == CampaignStatus.PENDING and h['closed_at']:
                days_passed = (current_trade_date - h['closed_at']).days

                if days_passed > self.max_gap_days:
                    # In der DB auf CLOSED setzen
                    # Wir "schummeln": Das end_date ist NICHT heute,
                    # sondern der Zeitpunkt der letzten Aktivität.
                    actual_end_date = h['closed_at']
                    self._update_campaign_status_in_db(
                        h['campaign_id'],
                        CampaignStatus.CLOSED,
                        closed_at=actual_end_date
                    )

                    # Im Speicher entfernen oder auf CLOSED setzen
                    # Wir entfernen es aus self.holdings, damit beim nächsten Trade
                    # für dieses Symbol zwingend eine NEUE Kampagne startet.
                    del self.holdings[symbol]

                    self.db_logger.info(
                        f"[FINAL CLOSE] {symbol}: Kampagne {h['campaign_id']} nach {days_passed} Tagen Inaktivität geschlossen.")

    def close_old_pending_campaigns(self, reference_date=None):
        """
        Sucht in der DB nach PENDING Kampagnen, die abgelaufen sind,
        und setzt sie auf CLOSED.
        """
        if reference_date is None:
            reference_date = datetime.now().date()
        elif hasattr(reference_date, 'date'):
            reference_date = reference_date.date()

        full_table_name = self._prefixed(TABLE_TRADING_CAMPAIGNS)

        # Berechne das Datum, ab dem eine Kampagne als abgelaufen gilt
        expiry_limit = reference_date - timedelta(days=self.max_gap_days)

        # Wir setzen den Status auf CLOSED und schreiben das end_date
        # (den letzten Trade-Tag) in das Feld closed_at.
        sql = f"""
            UPDATE {full_table_name}
            SET status = 'CLOSED',
                closed_at = end_date
            WHERE status = 'PENDING' 
            AND end_date < :expiry_limit
        """

        param_dict = {"expiry_limit": expiry_limit}
        rows_affected = self.db_conn.execute_write(sql, param_dict)

        if rows_affected > 0:
            self.db_logger.info(f"[CLEANUP] {rows_affected} abgelaufene PENDING-Kampagnen wurden auf CLOSED gesetzt.")
            # Wichtig: Danach den Speicher (holdings) neu laden, falls schon was drin war
            self.holdings = self._load_active_campaigns_from_db()

    def process_row_and_get_campaign(self, row):
        # FALLBACK LOGIK:
        # Wenn underlyingSymbol leer ist (bei Aktien), nimm das normale symbol
        symbol = row.get('underlyingSymbol')
        if not symbol or symbol.strip() == "":
            symbol = row.get('symbol')

        # Falls immer noch leer (Sicherheitscheck)
        if not symbol:
            self.db_logger.info(f"WARNUNG: Kein Symbol für Row gefunden: {row}")
            return 0

        qty = to_decimal(row['quantity'])
        asset_type = row['assetCategory']
        trade_date = row['dateTime']

        if not trade_date:
            self.db_logger.warning(f"dateTime fehlt für {symbol} ({asset_type}) — Trade übersprungen")
            return 0

        # 1. Sicherstellen, dass das Symbol im Speicher existiert
        if symbol not in self.holdings:
            # Falls das Script gerade erst gestartet ist, wird hier initialisiert
            self.holdings[symbol] = {
                'shares': 0, 'options': 0, 'campaign_id': None,
                'closed_at': None, 'status': None, 'pending_link_id': None
            }

        h = self.holdings[symbol]

        # --- KAMPAGNEN LOGIK (Start / Reaktivierung) ---
        if qty != 0:
            # Fall A: Reaktivierung einer PENDING Kampagne
            if h['campaign_id'] is not None and h['status'] == CampaignStatus.PENDING:
                days_passed = (trade_date - h['closed_at']).days
                if days_passed <= self.max_gap_days:
                    # REAKTIVIERUNG
                    h['status'] = CampaignStatus.ACTIVE
                    h['closed_at'] = None
                    self._update_campaign_status_in_db(
                        h['campaign_id'],
                        CampaignStatus.ACTIVE,
                        closed_at=None
                    )
                else:
                    # ABGELAUFEN -> Die alte Kampagne muss jetzt offiziell CLOSED werden
                    actual_end_date = h['closed_at']
                    self._update_campaign_status_in_db(
                        h['campaign_id'],
                        CampaignStatus.CLOSED,
                        closed_at=actual_end_date
                    )
                    self.db_logger.info(f"Kampagne abgelaufen: ID {h['campaign_id']} CLOSED")

                    # NEUSTART
                    strategy = self._determine_strategy(asset_type, qty)
                    h['campaign_id'] = self._insert_new_campaign_into_db(symbol, trade_date, strategy, asset_type)
                    h['status'] = CampaignStatus.ACTIVE
                    h['closed_at'] = None
                    h['shares'], h['options'] = 0, 0
                    self.db_logger.info(f"Neue Kampagne gestartet: Symbol {symbol}, ID {h['campaign_id']}")

            # Fall B: Initialer Start
            elif h['campaign_id'] is None:
                strategy = self._determine_strategy(asset_type, qty)
                h['campaign_id'] = self._insert_new_campaign_into_db(symbol, trade_date, strategy, asset_type)
                h['status'] = CampaignStatus.ACTIVE
                h['closed_at'] = None
                h['shares'], h['options'] = 0, 0
                self.db_logger.info(f"Neue Kampagne gestartet: Symbol {symbol}, ID {h['campaign_id']}")

        # --- INVENTORY UPDATE ---
        if asset_type == AssetCategory.STOCK:
            h['shares'] = to_decimal(h['shares']) + qty
        elif asset_type == AssetCategory.OPTION:
            # Achtung: 'status' Spalte in Raw muss für Expiration geprüft werden
            if row.get('status') == 'Expiration':
                h['options'] = Decimal('0')
            else:
                h['options'] = to_decimal(h['options']) + qty

        # --- STATUS-CHECK (Wann gehen wir Flat?) ---
        is_flat = (h['shares'] == 0 and h['options'] == 0)
        if is_flat and h['status'] == CampaignStatus.ACTIVE:
            h['status'] = CampaignStatus.PENDING
            h['closed_at'] = trade_date
            actual_end_date = h['closed_at']
            self._update_campaign_status_in_db(
                h['campaign_id'],
                CampaignStatus.PENDING,
                closed_at=actual_end_date
            )
        return h['campaign_id']

    @staticmethod
    def _generate_campaign_name(symbol, strategy, start_date):
        """
        Erzeugt einen lesbaren Namen wie: 'WHEEL: NVDA (2023-10-12)'
        """
        # Formatierung des Datums (nur Jahr-Monat-Tag)
        date_str = start_date.strftime('%Y-%m-%d') if start_date else 'unbekannt'

        # Mapping für schönere Strategie-Namen
        friendly_names = {
            'BONUS/CASHFLOW': 'Bonus',
            'DIRECT_INVEST': 'Stock',
            'HEDGE/SPECULATION': 'Option',
            'OTHER': 'Trade'
        }
        prefix = friendly_names.get(strategy, 'Misc')
        return f"{prefix}: {symbol} ({date_str})"

    def _insert_new_campaign_into_db(self, symbol, start_date, strategy, asset_type):
        full_table_name = self._prefixed(TABLE_TRADING_CAMPAIGNS)

        campaign_name = self._generate_campaign_name(symbol, strategy, start_date)

        sql = f"""
            INSERT INTO {full_table_name} (name, symbol, strategy, assetCategory, status, start_date, environment)
            VALUES (:name, :symbol, :strategy, :asset_type, 'ACTIVE', :start_date, :environment)
        """
        param_dict = {
            "name": campaign_name,
            "symbol": symbol,
            "strategy": strategy,
            "asset_type": asset_type,
            "start_date": start_date,
            "environment": self.env
        }
        return self.db_conn.insert_and_get_id(sql, param_dict)

    def _update_campaign_status_in_db(self, campaign_id, status, closed_at=None):
        full_table_name = self._prefixed(TABLE_TRADING_CAMPAIGNS)
        sql = f"UPDATE {full_table_name} SET status = :status, closed_at = :closed_at WHERE id = :id"
        param_dict = {"status": status, "id": campaign_id, "closed_at": closed_at}
        return self.db_conn.execute_write(sql, param_dict)

    def run_audit(self):
        """
        Vergleicht die Bestände im Speicher (holdings) mit der
        Summe aller Ledger-Einträge in der Datenbank.
        """
        self.db_logger.info("\n--- STARTING INVENTORY AUDIT ---")
        full_ledger_table = self._prefixed(TABLE_CAMPAIGN_LEDGER)

        # 1. Alle Summen direkt aus der DB holen
        sql = text(f"""
            SELECT 
                campaign_id,
                SUM(CASE WHEN assetCategory = 'STK' THEN inventory_delta ELSE 0 END) as db_shares,
                SUM(CASE WHEN assetCategory = 'OPT' THEN inventory_delta ELSE 0 END) as db_options
            FROM {full_ledger_table}
            GROUP BY campaign_id
        """)

        db_results = self.db_conn.fetch_all(sql)

        # Wir mappen die DB-Ergebnisse auf die campaign_id für schnellen Zugriff
        db_inventory = {res['campaign_id']: res for res in db_results}

        # 2. Durch alle aktiven Holdings im Speicher loopen
        for symbol, h in self.holdings.items():
            c_id = h['campaign_id']
            if not c_id:
                continue

            # Bestände aus der DB für diese ID holen (oder 0 wenn kein Ledger-Eintrag existiert)
            db_data = db_inventory.get(c_id, {'db_shares': 0, 'db_options': 0})

            diff_shares = to_decimal(h['shares']) - to_decimal(db_data['db_shares'])
            diff_options = to_decimal(h['options']) - to_decimal(db_data['db_options'])

            if abs(diff_shares) > Decimal('0.0001') or abs(diff_options) > Decimal('0.0001'):
                self.db_logger.info(f"⚠️ AUDIT WARNING für {symbol} (ID: {c_id}):")
                self.db_logger.info(f"   Speicher: Shares {h['shares']}, Options {h['options']}")
                self.db_logger.info(f"   Ledger:   Shares {db_data['db_shares']}, Options {db_data['db_options']}")
                self.db_logger.info(f"   DIFFERENZ: Shares {diff_shares}, Options {diff_options}")
            else:
                self.db_logger.info(f"✅ {symbol} (ID: {c_id}): OK")

        self.db_logger.info("--- AUDIT FINISHED ---\n")

    def _get_running_totals(self, campaign_id: int) -> dict:
        """Liest die aktuellen kumulierten Salden für eine Kampagne aus dem Ledger."""
        full_table_name = self._prefixed(TABLE_CAMPAIGN_LEDGER)
        sql = f"""
            SELECT
                COALESCE(SUM(realized_pnl), 0) AS cum_pnl,
                COALESCE(SUM(commission),   0) AS cum_commission,
                COALESCE(SUM(proceeds),     0) AS cum_premium
            FROM {full_table_name}
            WHERE campaign_id = :campaign_id
        """
        result = self.db_conn.fetch_one(sql, {"campaign_id": campaign_id})
        return {
            "cum_pnl":        to_decimal(result["cum_pnl"]        or 0),
            "cum_commission": to_decimal(result["cum_commission"]  or 0),
            "cum_premium":    to_decimal(result["cum_premium"]     or 0),
        }

    def link_to_campaign_new(self, assetCategory, campaign_id, source_table, source_id,
                             netcash, proceeds, commission, pnl, quantity, action, dateTime, conid,
                             currency='USD', fxRateToBase=1, symbol=None,
                             trade_price=None, strike=None, expiry=None,
                             multiplier=None, put_call=None, buy_sell=None,
                             link_id=None):

        totals = self._get_running_totals(campaign_id)
        new_cum_pnl        = totals["cum_pnl"]        + to_decimal(pnl)
        new_cum_commission = totals["cum_commission"]  + to_decimal(commission)
        new_cum_premium    = totals["cum_premium"]     + to_decimal(proceeds)

        full_table_name = self._prefixed(TABLE_CAMPAIGN_LEDGER)
        sql_ledger = f"""
            INSERT INTO {full_table_name}
            (assetCategory, campaign_id, symbol, source_table, source_id,
             linkID, tradePrice, strike, expiry, multiplier, putCall, buySell,
             netcash, proceeds, commission, realized_pnl,
             cum_pnl, cum_commission, cum_premium,
             inventory_delta, action, dateTime, conid, environment, currency, fxRateToBase,
             netcash_eur, proceeds_eur, commission_eur)
            VALUES
            (:assetCategory, :campaign_id, :symbol, :source_table, :source_id,
             :link_id, :trade_price, :strike, :expiry, :multiplier, :put_call, :buy_sell,
             :netcash, :proceeds, :commission, :realized_pnl,
             :cum_pnl, :cum_commission, :cum_premium,
             :inventory_delta, :action, :dateTime, :conid, :environment, :currency, :fxRateToBase,
             :netcash_eur, :proceeds_eur, :commission_eur)
        """
        fx = to_decimal(fxRateToBase) if fxRateToBase else to_decimal(1)
        params = {
            "assetCategory": assetCategory,
            "campaign_id": campaign_id,
            "symbol": symbol,
            "source_table": source_table,
            "source_id": source_id,
            "link_id": link_id,
            "trade_price": trade_price,
            "strike": strike,
            "expiry": expiry,
            "multiplier": multiplier,
            "put_call": put_call,
            "buy_sell": buy_sell,
            "netcash": netcash,
            "proceeds": proceeds,
            "commission": commission,
            "realized_pnl": pnl,
            "cum_pnl":        new_cum_pnl,
            "cum_commission": new_cum_commission,
            "cum_premium":    new_cum_premium,
            "inventory_delta": quantity,
            "action": action,
            "dateTime": dateTime,
            "conid": conid,
            "environment": self.env,
            "currency": currency or 'USD',
            "fxRateToBase": fx,
            "netcash_eur":    to_decimal(netcash)    * fx,
            "proceeds_eur":   to_decimal(proceeds)   * fx,
            "commission_eur": to_decimal(commission) * fx,
        }
        self.db_conn.execute_write(sql_ledger, params)

        # 2. Zeitstempel in der Hauptkampagne aktualisieren
        # full_table_name = self._prefixed(TABLE_TRADING_CAMPAIGNS)
        # sql_update_campaign = f"""
        #     UPDATE {full_table_name}
        #     SET end_date = dateTime
        #     WHERE id = :id
        # """
        # param_dict = {"id": campaign_id}
        # return self.db_conn.execute_write(sql_update_campaign, param_dict)

        full_table_name = self._prefixed(TABLE_TRADING_CAMPAIGNS)
        sql = f"UPDATE {full_table_name} SET end_date = :end_date WHERE id = :id"
        param_dict = {"id": campaign_id, "end_date": dateTime}
        return self.db_conn.execute_write(sql, param_dict)
