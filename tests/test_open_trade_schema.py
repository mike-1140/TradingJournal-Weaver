# Regressionstests fuer dokumentierte, bereits gefixte Bugs in OpenTradeSchema
# (siehe TradingJournal-Weaver/CLAUDE.md "Known Bugs"). Ohne diese Tests kann derselbe Fehler
# unbemerkt zurueckkehren -- eigener Refactor, externer PR oder eine Nachbar-
# Aenderung, die die Funktion nur indirekt beruehrt.

from decimal import Decimal
from datetime import datetime

from src.trade_schemas.open_trade import OpenTradeSchema
from src.trade_enums import TradeStatus


def _open_trade(**overrides):
    base = {
        "symID": 1,
        "assetCategory": "OPT",
        "symbol": "XYZ",
        "description": "XYZ 20260220 P 50",
        "quantity": Decimal("-10"),
        "tradePrice": Decimal("2.50"),
        "netCash": Decimal("2500"),
        "proceeds": Decimal("2500"),
        "ibCommission": Decimal("-6.50"),
        "dateTime": datetime(2026, 1, 5),
        "currency": "USD",
        "fxRateToBase": Decimal("1"),
        "tradeID": "OPEN1",
        "buySell": "SELL",
    }
    base.update(overrides)
    return base


def _close_data(**overrides):
    base = {
        "quantity": Decimal("6"),
        "tradePrice": Decimal("1.00"),
        "netCash": Decimal("-600"),
        "proceeds": Decimal("-600"),
        "ibCommission": Decimal("-3.90"),
        "dateTime": datetime(2026, 1, 10),
        "buySell": "BUY",
        "status": "Closed",
        "tradeID": "CLOSE1",
    }
    base.update(overrides)
    return base


class TestPartialCloseSkalierung:
    """Bug 1 (behoben 2026-02-27): profit_close wurde nicht mit close_portion
    skaliert -> bei Teil-Closes ueber mehrere Tranchen kam ein Vielfaches des
    echten P&L raus."""

    def test_profit_wird_anteilig_zur_close_portion_berechnet(self):
        ratio = Decimal("6") / Decimal("10")  # 60% der Position werden geschlossen

        result = OpenTradeSchema.partial_close_new_open(_open_trade(), _close_data(), ratio)

        erwarteter_profit = Decimal("2500") * ratio + Decimal("-600")
        assert result["profit"] == erwarteter_profit

    def test_commission_wird_anteilig_zur_close_portion_berechnet(self):
        ratio = Decimal("6") / Decimal("10")

        result = OpenTradeSchema.partial_close_new_open(_open_trade(), _close_data(), ratio)

        erwartete_commission = Decimal("-6.50") * ratio + Decimal("-3.90")
        assert result["ibCommission"] == erwartete_commission


class TestROIBerechnung:
    """Bug 3 (behoben 2026-02-27): ROI nutzte einen falschen Nenner statt der
    tatsaechlichen Einstiegskosten (netCashOpen)."""

    def test_roi_nutzt_netcashopen_als_nenner(self):
        full_close = _close_data(quantity=Decimal("10"), netCash=Decimal("-1000"), proceeds=Decimal("-1000"))

        result = OpenTradeSchema.to_closed_trade(_open_trade(), full_close, Decimal("1"))

        erwarteter_roi = abs(result["profit"] / result["netCashOpen"]) * 100
        assert result["ROI"] == erwarteter_roi


class TestStatusValidierungMitEnum:
    """Enum-Bug (behoben 2026-05-06): Python 3.11+ aenderte str()-Verhalten fuer
    str-Enums -> str(TradeStatus.OPEN) wurde 'TradeStatus.OPEN' statt 'OPEN',
    validate() schlug faelschlich fehl."""

    def test_enum_status_wird_akzeptiert(self):
        errors = OpenTradeSchema.validate(_open_trade(status=TradeStatus.OPEN))

        assert "Invalid status for open trade" not in errors

    def test_ungueltiger_status_wird_weiterhin_abgelehnt(self):
        errors = OpenTradeSchema.validate(_open_trade(status="KOMPLETT_FALSCH"))

        assert "Invalid status for open trade" in errors
