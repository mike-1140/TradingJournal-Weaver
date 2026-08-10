# Ebene-2-Tests fuer process_raw_trade() -- die FIFO-Fallunterscheidung aus
# process_ibkr_trades.py (siehe Case-Tabelle in xml_proj/CLAUDE.md). Nutzt
# FakeTradeRepository/FakeInventoryTracker aus conftest.py statt echter DB.

from decimal import Decimal
from datetime import datetime

from src.process_ibkr_trades import process_raw_trade
from src.trade_enums import LedgerAction, TradeStatus
from src.config import TABLE_TRADES_RAW


def _raw_trade(**overrides):
    base = {
        "id": 501,
        "symbol": "ABC",
        "assetCategory": "STK",
        "quantity": Decimal("100"),
        "buySell": "BUY",
        "tradePrice": Decimal("50.00"),
        "netCash": Decimal("-5000"),
        "proceeds": Decimal("-5000"),
        "ibCommission": Decimal("-1.00"),
        "dateTime": datetime(2026, 1, 5),
        "conid": 12345,
        "currency": "USD",
        "fxRateToBase": Decimal("1"),
        "tradeID": "T501",
        "linkID": None,
        "strategy": None,
        "putCall": None,
        "strike": None,
        "expiry": None,
        "multiplier": None,
        "description": "ABC",
        "underlyingSymbol": None,
        "underlyingConid": None,
        "opt_strategy": None,
        "opt_strategyName": None,
        "opt_strategyID": None,
        "symID": None,
        "subCategory": None,
        "environment": "TEST",
        "fifoPnlRealized": None,
        "ibOrderID": None,
    }
    base.update(overrides)
    return base


def _seed_long_100(fake_repo, **overrides):
    fields = dict(
        symbol="ABC", assetCategory="STK", quantity=Decimal("100"),
        tradePrice=Decimal("50.00"), netCash=Decimal("-5000"), proceeds=Decimal("-5000"),
        ibCommission=Decimal("-1.00"), dateTime=datetime(2026, 1, 5),
        buySell="BUY", currency="USD", fxRateToBase=Decimal("1"), tradeID="T500",
    )
    fields.update(overrides)
    return fake_repo.seed_open_trade(**fields)


class TestCase1PositionEroeffnen:
    """Keine offene Tranche vorhanden -> neue Position wird als OPEN gebucht."""

    def test_erste_position_wird_als_open_gebucht(self, dummy_logger, fake_repo, fake_tracker):
        raw = _raw_trade()  # BUY 100 ABC

        process_raw_trade(dummy_logger, raw, fake_repo, fake_tracker, campaign_id=1)

        assert len(fake_repo._open_trades) == 1
        assert fake_repo._open_trades[0]["status"] == TradeStatus.OPEN
        assert fake_repo._open_trades[0]["quantity"] == Decimal("100")
        assert (TABLE_TRADES_RAW, 501) in fake_repo.processed

        [ledger_call] = fake_tracker.ledger_calls
        assert ledger_call["action"] == LedgerAction.STK_BUY
        assert ledger_call["quantity"] == Decimal("100")


class TestCase2cExactMatch:
    """Offene Tranche und Close-Trade heben sich genau auf -> voller Close."""

    def test_vollstaendiger_close_erzeugt_closed_trade_und_schliesst_tranche(
        self, dummy_logger, fake_repo, fake_tracker
    ):
        _seed_long_100(fake_repo)
        close = _raw_trade(
            id=502, quantity=Decimal("-100"), buySell="SELL",
            tradePrice=Decimal("55.00"), netCash=Decimal("5500"), proceeds=Decimal("5500"),
            ibCommission=Decimal("-1.10"), dateTime=datetime(2026, 1, 10), tradeID="T502",
        )

        process_raw_trade(dummy_logger, close, fake_repo, fake_tracker, campaign_id=1)

        assert len(fake_repo.closed_trades) == 1
        # Brutto-P&L = proceeds_open + proceeds_close (Commission wird separat gefuehrt)
        assert fake_repo.closed_trades[0]["profit"] == Decimal("500")
        assert fake_repo._open_trades[0]["processed"] == 1

        [ledger_call] = fake_tracker.ledger_calls
        assert ledger_call["action"] == LedgerAction.STK_SELL_CLOSE
        assert (TABLE_TRADES_RAW, 502) in fake_repo.processed


class TestCase2aTeilschluss:
    """Offene Tranche ist groesser als der Close -> Teilschluss + Rest-Tranche."""

    def test_teilschluss_schliesst_anteilig_und_bucht_rest_neu_ein(
        self, dummy_logger, fake_repo, fake_tracker
    ):
        _seed_long_100(fake_repo)
        close = _raw_trade(
            id=503, quantity=Decimal("-40"), buySell="SELL",
            tradePrice=Decimal("55.00"), netCash=Decimal("2200"), proceeds=Decimal("2200"),
            ibCommission=Decimal("-0.50"), dateTime=datetime(2026, 1, 10), tradeID="T503",
        )

        process_raw_trade(dummy_logger, close, fake_repo, fake_tracker, campaign_id=1)

        original, remainder = fake_repo._open_trades
        assert original["processed"] == 1
        assert remainder["status"] == TradeStatus.SPLIT_REST
        assert remainder["quantity"] == Decimal("60")  # 100 - 40

        assert len(fake_repo.closed_trades) == 1
        [ledger_call] = fake_tracker.ledger_calls
        assert ledger_call["action"] == LedgerAction.STK_SELL_PARTIAL


class TestCase2bUndReversal:
    """Close ist groesser als die offene Tranche -> Tranche komplett verbraucht,
    Rest wird als neue Gegenposition (REV_OPEN) eroeffnet."""

    def test_tranche_wird_komplett_verbraucht_rest_wird_reversal_open(
        self, dummy_logger, fake_repo, fake_tracker
    ):
        _seed_long_100(fake_repo, quantity=Decimal("30"), netCash=Decimal("-1500"),
                       proceeds=Decimal("-1500"), ibCommission=Decimal("-0.30"))
        close = _raw_trade(
            id=504, quantity=Decimal("-100"), buySell="SELL",
            tradePrice=Decimal("55.00"), netCash=Decimal("5500"), proceeds=Decimal("5500"),
            ibCommission=Decimal("-1.00"), dateTime=datetime(2026, 1, 10), tradeID="T504",
        )

        process_raw_trade(dummy_logger, close, fake_repo, fake_tracker, campaign_id=1)

        assert fake_repo._open_trades[0]["processed"] == 1
        assert len(fake_repo.closed_trades) == 1

        reversal = fake_repo._open_trades[1]
        assert reversal["status"] == TradeStatus.REV_OPEN
        assert reversal["quantity"] == Decimal("-70")  # 100 - 30, jetzt Short

        actions = [c["action"] for c in fake_tracker.ledger_calls]
        assert actions == [LedgerAction.STK_SELL_CLOSE, LedgerAction.TRADE_REVERSAL_OPEN]


class TestBug4LedgerKommissionNurCloseAnteil:
    """Bug 4 (behoben, laut Code-Kommentar 'Opening-Kommission bereits beim
    TRADE_OPEN gebucht'): die Ledger-Buchung beim Schliessen darf NIE einen
    Anteil der Open-Commission enthalten -- die wurde schon einmal komplett
    bei TRADE_OPEN gebucht. Ein erneutes (anteiliges) Einrechnen wuerde sie
    ueber mehrere Teilschluesse hinweg mehrfach zaehlen.

    Open-Commission wird hier bewusst auf einen riesigen Marker-Wert (-100)
    gesetzt, der mit keiner echten Close-Commission verwechselt werden kann --
    taucht er doch in der Ledger-Summe auf, faellt es sofort auf."""

    def test_case_2c_exact_match_bucht_nur_close_commission(self, dummy_logger, fake_repo, fake_tracker):
        _seed_long_100(fake_repo, ibCommission=Decimal("-100"))
        close = _raw_trade(
            id=601, quantity=Decimal("-100"), buySell="SELL",
            tradePrice=Decimal("55.00"), netCash=Decimal("5500"), proceeds=Decimal("5500"),
            ibCommission=Decimal("-5"), dateTime=datetime(2026, 1, 10), tradeID="T601",
        )

        process_raw_trade(dummy_logger, close, fake_repo, fake_tracker, campaign_id=1)

        [ledger_call] = fake_tracker.ledger_calls
        assert ledger_call["commission"] == Decimal("-5")

    def test_case_2a_teilschluss_bucht_nur_close_commission(self, dummy_logger, fake_repo, fake_tracker):
        _seed_long_100(fake_repo, ibCommission=Decimal("-100"))
        close = _raw_trade(
            id=602, quantity=Decimal("-40"), buySell="SELL",
            tradePrice=Decimal("55.00"), netCash=Decimal("2200"), proceeds=Decimal("2200"),
            ibCommission=Decimal("-5"), dateTime=datetime(2026, 1, 10), tradeID="T602",
        )

        process_raw_trade(dummy_logger, close, fake_repo, fake_tracker, campaign_id=1)

        [ledger_call] = fake_tracker.ledger_calls
        assert ledger_call["commission"] == Decimal("-5")

    def test_case_2b_bucht_nur_anteilige_close_commission(self, dummy_logger, fake_repo, fake_tracker):
        _seed_long_100(fake_repo, quantity=Decimal("30"), netCash=Decimal("-1500"),
                       proceeds=Decimal("-1500"), ibCommission=Decimal("-100"))
        close = _raw_trade(
            id=603, quantity=Decimal("-100"), buySell="SELL",
            tradePrice=Decimal("55.00"), netCash=Decimal("5500"), proceeds=Decimal("5500"),
            ibCommission=Decimal("-10"), dateTime=datetime(2026, 1, 10), tradeID="T603",
        )

        process_raw_trade(dummy_logger, close, fake_repo, fake_tracker, campaign_id=1)

        close_call = fake_tracker.ledger_calls[0]
        # Nur 30/100 der Close-Order entfallen auf diese Tranche -> Close-Commission
        # wird anteilig gebucht, die Open-Commission (-100) taucht nirgends auf.
        assert close_call["commission"] == Decimal("-10") * (Decimal("30") / Decimal("100"))


class TestBug2OptNormalCloseBuchtNetcash:
    """Bug 2 (behoben laut CLAUDE.md 'OPT normal close records zero cash in
    campaign ledger'): beim regulaeren Schliessen einer Option per Gegen-Order
    (buy-to-close/sell-to-close -- NICHT Expiration/Assignment/Cash-Settlement)
    wurden netcash/proceeds/commission im Ledger als 0 statt der tatsaechlichen
    Werte gebucht. Betrifft den 'else'-Zweig im OPT-Ast von Case 2c."""

    def test_normaler_buy_to_close_bucht_echten_cashflow(self, dummy_logger, fake_repo, fake_tracker):
        fake_repo.seed_open_trade(
            symbol="XYZ 260220P50", assetCategory="OPT", quantity=Decimal("-1"),
            putCall="P", strike=Decimal("50"), expiry=datetime(2026, 2, 20),
            multiplier=Decimal("100"), tradePrice=Decimal("2.50"),
            netCash=Decimal("250"), proceeds=Decimal("250"), ibCommission=Decimal("-0.65"),
            dateTime=datetime(2026, 1, 5), buySell="SELL", currency="USD",
            fxRateToBase=Decimal("1"), tradeID="O700",
        )
        close = _raw_trade(
            id=701, symbol="XYZ 260220P50", assetCategory="OPT", quantity=Decimal("1"),
            putCall="P", strike=Decimal("50"), expiry=datetime(2026, 2, 20), multiplier=Decimal("100"),
            buySell="BUY", tradePrice=Decimal("1.00"), netCash=Decimal("-100"),
            proceeds=Decimal("-100"), ibCommission=Decimal("-0.65"),
            dateTime=datetime(2026, 1, 10), tradeID="T701", status="Closed",
        )

        process_raw_trade(dummy_logger, close, fake_repo, fake_tracker, campaign_id=1)

        [ledger_call] = fake_tracker.ledger_calls
        assert ledger_call["action"] == LedgerAction.OPT_PUT_BUY_CLOSE
        assert ledger_call["netcash"] == Decimal("-100")
        assert ledger_call["proceeds"] == Decimal("-100")
        assert ledger_call["commission"] == Decimal("-0.65")
