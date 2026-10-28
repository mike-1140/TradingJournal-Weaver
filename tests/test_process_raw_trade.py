# Ebene-2-Tests fuer process_raw_trade() -- die FIFO-Fallunterscheidung aus
# process_ibkr_trades.py (siehe Case-Tabelle in TradingJournal-Weaver/CLAUDE.md). Nutzt
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


class TestAssignmentLinkIdNichtVerschleppen:
    """Regressionstest (gefunden 2026-10-25, OMEX in zwei Datenbestaenden): Beim Assignment
    merkt sich Case 2c die linkID als pending_link_id fuer den folgenden STK-Open. Wird der
    STK-Open derselben Zuteilung VOR dem Options-Close verarbeitet, bleibt die gemerkte ID
    liegen und landete beim naechsten STK-Open des Symbols -- sogar vor dessen eigener
    IBKR-linkID. Jetzt gilt: eigene linkID hat Vorrang, die gemerkte nur bei gleichem
    Zeitpunkt (dieselbe Zuteilung)."""

    SEPT = datetime(2024, 9, 20, 16, 20)
    OKT = datetime(2024, 10, 18, 16, 20)

    def _stk_buy(self, raw_id, dt, link_id):
        return _raw_trade(id=raw_id, symbol="OMEX", dateTime=dt, tradeID=f"S{raw_id}",
                          linkID=link_id, conid=111)

    def _assign_put(self, fake_repo, raw_id, dt, link_id):
        fake_repo.seed_open_trade(
            symbol=f"OMEX P{raw_id}", assetCategory="OPT", quantity=Decimal("-1"),
            putCall="P", strike=Decimal("3"), expiry=dt, multiplier=Decimal("100"),
            tradePrice=Decimal("0.20"), netCash=Decimal("20"), proceeds=Decimal("20"),
            ibCommission=Decimal("-0.65"), dateTime=datetime(2024, 8, 1), buySell="SELL",
            currency="USD", fxRateToBase=Decimal("1"), tradeID=f"O{raw_id}",
            underlyingSymbol="OMEX",
        )
        return _raw_trade(
            id=raw_id, symbol=f"OMEX P{raw_id}", assetCategory="OPT", quantity=Decimal("1"),
            putCall="P", strike=Decimal("3"), expiry=dt, multiplier=Decimal("100"),
            buySell="BUY", tradePrice=Decimal("0"), netCash=Decimal("0"), proceeds=Decimal("0"),
            ibCommission=Decimal("0"), dateTime=dt, tradeID=f"T{raw_id}", status="Assigned",
            underlyingSymbol="OMEX", linkID=link_id, conid=222,
        )

    def test_naechste_zuteilung_behaelt_eigene_linkid(self, dummy_logger, fake_repo, fake_tracker):
        fake_tracker.holdings["OMEX"] = {}
        # Sept: Aktie vor Option verarbeitet (gleicher Zeitstempel)
        process_raw_trade(dummy_logger, self._stk_buy(801, self.SEPT, "L-SEPT"), fake_repo, fake_tracker, campaign_id=1)
        process_raw_trade(dummy_logger, self._assign_put(fake_repo, 802, self.SEPT, "L-SEPT"), fake_repo, fake_tracker, campaign_id=1)
        # Okt: naechste Zuteilung, wieder Aktie zuerst
        process_raw_trade(dummy_logger, self._stk_buy(803, self.OKT, "L-OKT"), fake_repo, fake_tracker, campaign_id=1)

        stk_links = [c["link_id"] for c in fake_tracker.ledger_calls if c["action"] == LedgerAction.STK_BUY]
        assert stk_links == ["L-SEPT", "L-OKT"]

    def test_liegengebliebene_id_landet_nicht_bei_spaeterem_normalkauf(self, dummy_logger, fake_repo, fake_tracker):
        fake_tracker.holdings["OMEX"] = {}
        process_raw_trade(dummy_logger, self._stk_buy(811, self.SEPT, "L-SEPT"), fake_repo, fake_tracker, campaign_id=1)
        process_raw_trade(dummy_logger, self._assign_put(fake_repo, 812, self.SEPT, "L-SEPT"), fake_repo, fake_tracker, campaign_id=1)
        # spaeterer normaler Kauf ohne linkID
        process_raw_trade(dummy_logger, self._stk_buy(813, self.OKT, None), fake_repo, fake_tracker, campaign_id=1)

        last_buy = [c for c in fake_tracker.ledger_calls if c["action"] == LedgerAction.STK_BUY][-1]
        assert not last_buy["link_id"]

    def test_option_vor_aktie_verknuepft_weiterhin(self, dummy_logger, fake_repo, fake_tracker):
        """Normalfall: Option zuerst, Aktie ohne eigene linkID -> bekommt die gemerkte ID."""
        fake_tracker.holdings["OMEX"] = {}
        process_raw_trade(dummy_logger, self._assign_put(fake_repo, 821, self.SEPT, None), fake_repo, fake_tracker, campaign_id=1)
        process_raw_trade(dummy_logger, self._stk_buy(822, self.SEPT, None), fake_repo, fake_tracker, campaign_id=1)

        opt_call, stk_call = fake_tracker.ledger_calls
        assert opt_call["action"] == LedgerAction.OPTION_EXERCISE
        assert opt_call["link_id"] and stk_call["link_id"] == opt_call["link_id"]


class TestCashDevisentauschOhneLedger:
    """Der FX-Ledger-Zweig (FX_EXCHANGE_FROM_/TO_) wurde 2026-10-26 entfernt: er buchte nur mit
    campaign_id, CASH-Trades bekommen aber nie eine -- lief also nie. Devisentausche stehen in
    trades_fx. Ein CASH-Raw-Trade wird nur als verarbeitet markiert, auch wenn (theoretisch)
    eine campaign_id mitkaeme."""

    def test_cash_trade_wird_nur_als_verarbeitet_markiert(self, dummy_logger, fake_repo, fake_tracker):
        for qty in (Decimal("1"), Decimal("2")):  # 1 = "von"-Seite, 2 = "nach"-Seite
            raw = _raw_trade(id=900 + int(qty), symbol="EUR.USD", assetCategory="CASH",
                             quantity=qty, tradePrice=Decimal("1.08"), tradeID=f"FX{qty}")
            process_raw_trade(dummy_logger, raw, fake_repo, fake_tracker, campaign_id=5)

        assert fake_tracker.ledger_calls == []
        assert fake_repo._open_trades == []
        assert (TABLE_TRADES_RAW, 901) in fake_repo.processed
        assert (TABLE_TRADES_RAW, 902) in fake_repo.processed


class TestOptionsStatusBeiTeilschliessung:
    """Regressionstest (gefunden 2026-10-20, behoben 2026-10-28): Fall 2a (Teilschliessung) und
    2b (Schliessung ueber mehrere Tranchen) setzten den Status pauschal auf 'Closed' und buchten
    eine normale Schliessung -- ein verfallener/zugeteilter/barausgeglichener Leg verlor damit
    Expired/Assigned/CashSettled, im Ledger fehlte OPTION_EXPIRATION/_EXERCISE/CASH_SETTLEMENT,
    bei Teil-Zuteilung fehlte die gemerkte linkID fuer die Aktie. Echtdaten: SPXW-Spreads mit
    2 Kontrakten, als 2 Tranchen eroeffnet und in einer Buchung verfallen."""

    EXPIRY = datetime(2025, 9, 11, 16, 20)

    def _seed_short_put(self, fake_repo, qty, trade_id):
        return fake_repo.seed_open_trade(
            symbol="SPXW P6545", assetCategory="OPT", quantity=Decimal(qty), putCall="P",
            strike=Decimal("6545"), expiry=self.EXPIRY, multiplier=Decimal("100"),
            tradePrice=Decimal("1.00"), netCash=Decimal("100") * -Decimal(qty),
            proceeds=Decimal("100") * -Decimal(qty), ibCommission=Decimal("-1.00"),
            dateTime=datetime(2025, 9, 10, 10, 0), buySell="SELL", currency="USD",
            fxRateToBase=Decimal("1"), tradeID=trade_id, underlyingSymbol="SPXW",
        )

    def _event(self, qty, status, link_id=None, **extra):
        return _raw_trade(
            id=950, symbol="SPXW P6545", assetCategory="OPT", quantity=Decimal(qty), putCall="P",
            strike=Decimal("6545"), expiry=self.EXPIRY, multiplier=Decimal("100"), buySell="BUY",
            tradePrice=Decimal("0"), netCash=Decimal("0"), proceeds=Decimal("0"),
            ibCommission=Decimal("0"), dateTime=self.EXPIRY, tradeID="E950", status=status,
            linkID=link_id, underlyingSymbol="SPXW", **extra,
        )

    def test_verfall_ueber_zwei_tranchen_fall_2b(self, dummy_logger, fake_repo, fake_tracker):
        self._seed_short_put(fake_repo, "-1", "O1")
        self._seed_short_put(fake_repo, "-1", "O2")

        process_raw_trade(dummy_logger, self._event("2", "Expired"), fake_repo, fake_tracker, campaign_id=1)

        assert [c["status"] for c in fake_repo.closed_trades] == ["Expired", "Expired"]
        assert [c["action"] for c in fake_tracker.ledger_calls] == [LedgerAction.OPTION_EXPIRATION] * 2

    def test_teil_verfall_fall_2a(self, dummy_logger, fake_repo, fake_tracker):
        self._seed_short_put(fake_repo, "-2", "O1")

        process_raw_trade(dummy_logger, self._event("1", "Expired"), fake_repo, fake_tracker, campaign_id=1)

        [closed] = fake_repo.closed_trades
        assert closed["status"] == "Expired"
        [ledger_call] = fake_tracker.ledger_calls
        assert ledger_call["action"] == LedgerAction.OPTION_EXPIRATION

    def test_teil_zuteilung_merkt_linkid_fuer_die_aktie(self, dummy_logger, fake_repo, fake_tracker):
        fake_tracker.holdings["SPXW"] = {}
        self._seed_short_put(fake_repo, "-2", "O1")

        process_raw_trade(dummy_logger, self._event("1", "Assigned", link_id="L-TEIL"), fake_repo, fake_tracker, campaign_id=1)

        [closed] = fake_repo.closed_trades
        assert closed["status"] == "Assigned"
        [ledger_call] = fake_tracker.ledger_calls
        assert ledger_call["action"] == LedgerAction.OPTION_EXERCISE
        assert ledger_call["link_id"] == "L-TEIL"
        assert fake_tracker.holdings["SPXW"]["pending_link_id"] == "L-TEIL"

    def test_barausgleich_ueber_zwei_tranchen(self, dummy_logger, fake_repo, fake_tracker):
        self._seed_short_put(fake_repo, "-1", "O1")
        self._seed_short_put(fake_repo, "-1", "O2")
        event = self._event("2", "CashSettled")
        event.update(netCash=Decimal("-1500"), proceeds=Decimal("-1500"))

        process_raw_trade(dummy_logger, event, fake_repo, fake_tracker, campaign_id=1)

        assert [c["status"] for c in fake_repo.closed_trades] == ["CashSettled", "CashSettled"]
        assert [c["action"] for c in fake_tracker.ledger_calls] == [LedgerAction.CASH_SETTLEMENT] * 2
        # das bewegte Cash bleibt in der Buchung (je Tranche die Haelfte)
        assert sum(c["netcash"] for c in fake_tracker.ledger_calls) == Decimal("-1500")
