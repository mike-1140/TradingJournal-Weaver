# Regressionstest fuer den Split-Bug (behoben 2026-05-11): Kampagne blieb nach
# einem Stock Split faelschlich ACTIVE, weil das falsche Symbol im
# tracker.holdings-Dict nachgeschlagen wurde. Die urspruengliche Buglogik sass
# inline in process_trades() (nicht ohne echte DB aufrufbar) -- dafuer wurde
# die eine betroffene Entscheidung in _resolve_split_holdings_symbol()
# extrahiert (verhaltensgleich, siehe Docstring dort).

from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from src.process_ibkr_trades import _handle_split_trade, _resolve_split_holdings_symbol, process_stock_split


class TestSplitSymbolAufloesung:
    def test_nutzt_das_neue_symbol_nach_dem_split(self):
        # _handle_split_trade() hat trade['symbol'] bereits auf das neue
        # Symbol gesetzt (siehe apply_split()).
        trade = {"symbol": "APDN", "underlyingSymbol": "APDN.OLD"}

        assert _resolve_split_holdings_symbol(trade) == "APDN"

    def test_ignoriert_das_veraltete_underlying_symbol(self):
        # Regressionstest: die fruehere Fassung loeste 'underlyingSymbol or
        # symbol' auf -- damit haette dieser Fall faelschlich "APDN.OLD"
        # zurueckgegeben, tracker.holdings.get() waere ins Leere gelaufen und
        # die Kampagne nie als flach erkannt worden.
        trade = {"symbol": "APDN", "underlyingSymbol": "APDN.OLD"}

        result = _resolve_split_holdings_symbol(trade)

        assert result != "APDN.OLD"

    def test_funktioniert_auch_ohne_gesetztes_underlying_symbol(self):
        trade = {"symbol": "APDN"}

        assert _resolve_split_holdings_symbol(trade) == "APDN"


class _SplitRepo:
    def __init__(self, tranches=()):
        self.tranches = list(tranches)
        self.updated = []
        self.marked = []

    def get_open_trades(self, asset_category, symbol):
        return self.tranches

    def update_open_trade(self, updates):
        self.updated.append(updates)

    def mark_trade_processed(self, table, trade_id):
        self.marked.append((table, trade_id))


class _SplitTracker:
    def __init__(self):
        self.entries = []

    def link_to_campaign_new(self, **kwargs):
        self.entries.append(kwargs)


class TestSplitDatumImLedger:
    def test_ledger_traegt_das_split_datum_nicht_das_kaufdatum(self):
        # Regressionstest: der Eintrag trug das Eroeffnungsdatum der Tranche und stand
        # damit vor Trades, die tatsaechlich vor dem Split lagen.
        tranche = {"id": 1, "symbol": "ABC", "assetCategory": "STK", "quantity": Decimal("400"),
                   "tradePrice": Decimal("0.5"), "dateTime": datetime(2026, 10, 26, 15, 12, 35)}
        trade = {"symbol": "ABC", "assetCategory": "STK", "multiplier": Decimal("0.04"),
                 "dateTime": datetime(2026, 10, 29)}
        repo, tracker = _SplitRepo([tranche]), _SplitTracker()

        process_stock_split(repo, trade, tracker, campaign_id=7)

        assert tracker.entries[0]["dateTime"] == datetime(2026, 10, 29)
        assert tracker.entries[0]["quantity"] == Decimal("-384")
        assert repo.updated[0]["quantity"] == Decimal("16")
        assert repo.updated[0]["tradePrice"] == Decimal("12.5")


class TestSplitTeileWerdenMarkiert:
    def test_beide_teile_sind_nach_dem_lauf_verarbeitet(self):
        # Regressionstest: der zweite Teil blieb auf processed=0 stehen.
        old = {"id": 11, "actionID": "A", "symbol": "ABC.OLD", "quantity": Decimal("-400")}
        new = {"id": 12, "actionID": "A", "symbol": "ABC", "quantity": Decimal("16")}
        repo, buffer = _SplitRepo(), defaultdict(list)

        assert _handle_split_trade(new, buffer, repo, "raw") == "waiting"
        assert _handle_split_trade(old, buffer, repo, "raw") == "processed"

        assert repo.marked == [("raw", 12), ("raw", 11)]
        assert old["symbol"] == "ABC"
        assert old["multiplier"] == Decimal("0.04")
