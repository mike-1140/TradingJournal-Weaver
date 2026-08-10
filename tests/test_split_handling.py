# Regressionstest fuer den Split-Bug (behoben 2026-05-11): Kampagne blieb nach
# einem Stock Split faelschlich ACTIVE, weil das falsche Symbol im
# tracker.holdings-Dict nachgeschlagen wurde. Die urspruengliche Buglogik sass
# inline in process_trades() (nicht ohne echte DB aufrufbar) -- dafuer wurde
# die eine betroffene Entscheidung in _resolve_split_holdings_symbol()
# extrahiert (verhaltensgleich, siehe Docstring dort).

from src.process_ibkr_trades import _resolve_split_holdings_symbol


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
