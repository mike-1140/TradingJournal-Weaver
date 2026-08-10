# Regressionstest fuer den Kampagnen-Gap-Bug (behoben 2026-05-27):
# close_old_pending_campaigns() lief mit datetime.now() statt dem Datum des
# ersten zu verarbeitenden Trades -> bei verzoegertem AUTOM-Import (Trades
# werden erst Wochen spaeter importiert) wurden PENDING-Kampagnen faelschlich
# als abgelaufen geschlossen, obwohl sie aus Sicht der Trade-Historie noch
# innerhalb des Gap-Fensters lagen. Ergebnis: doppelte Kampagnen.

from datetime import datetime, date, timedelta

from src.parsers.inventory_tracker import InventoryTracker


class FakeInventoryDbConn:
    """
    Nur fuer close_old_pending_campaigns()-Tests: zeichnet execute_write()-
    Aufrufe auf (SQL-Text + Params) statt echtes SQL auszufuehren.
    fetch_all() liefert immer eine leere Liste (keine aktiven Kampagnen),
    damit der Tracker beim Konstruieren nicht gegen eine echte DB laeuft.
    """
    def __init__(self):
        self.write_calls = []  # Liste von (sql, params)

    def execute_write(self, sql, params=None):
        self.write_calls.append((sql, params or {}))
        return 0  # keine betroffenen Zeilen -> kein Reload der Holdings noetig

    def fetch_all(self, sql, params=None):
        return []


class TestCloseOldPendingCampaigns:
    def test_expiry_limit_wird_aus_reference_date_berechnet_nicht_aus_heute(self, dummy_logger):
        fake_db = FakeInventoryDbConn()
        # Trades werden mit Verzoegerung importiert -- der erste Trade dieses
        # Laufs liegt Monate vor dem heutigen Systemdatum.
        erster_trade_dieses_laufs = datetime(2026, 1, 15, 9, 30)
        max_gap_days = 10

        InventoryTracker(
            dummy_logger, fake_db, table_prefix="test_", env="TEST",
            max_gap_days=max_gap_days, reference_date=erster_trade_dieses_laufs,
        )

        [(_, params)] = fake_db.write_calls
        assert params["expiry_limit"] == date(2026, 1, 15) - timedelta(days=max_gap_days)

    def test_ohne_reference_date_faellt_es_auf_heute_zurueck(self, dummy_logger):
        # Legitimer Default fuer interaktive/manuelle Aufrufe ohne Trade-Kontext.
        fake_db = FakeInventoryDbConn()

        InventoryTracker(dummy_logger, fake_db, table_prefix="test_", env="TEST", max_gap_days=10)

        [(_, params)] = fake_db.write_calls
        assert params["expiry_limit"] == date.today() - timedelta(days=10)
