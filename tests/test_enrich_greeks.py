# Tests fuer den Pipeline-Schritt "enrich" (src/enrich_greeks.py): Rechenteil (Black-Scholes, IV,
# IVR/IVP), Auswahl der Trades, Zuordnung der Basiswerte und Verhalten ohne TWS. Keine TWS und
# keine Datenbank noetig -- die TWS-Abfragen werden durch eine nachgebaute Quelle ersetzt.

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from src import enrich_greeks as eg

ET = ZoneInfo("America/New_York")


class TestBlackScholes:
    """Referenzwerte: S=100, K=100, T=1, r=5 %, sigma=20 % -> Call 10.4506, Put 5.5735, Delta Call 0.6368."""

    def test_preise_und_delta(self):
        assert eg.bs_price(100, 100, 1, 0.2, put=False, rate=0.05) == pytest.approx(10.4506, abs=1e-4)
        assert eg.bs_price(100, 100, 1, 0.2, put=True, rate=0.05) == pytest.approx(5.5735, abs=1e-4)
        assert eg.bs_delta(100, 100, 1, 0.2, put=False, rate=0.05) == pytest.approx(0.6368, abs=1e-4)
        assert eg.bs_delta(100, 100, 1, 0.2, put=True, rate=0.05) == pytest.approx(0.6368 - 1, abs=1e-4)

    def test_iv_aus_preis_rundreise(self):
        price = eg.bs_price(4780, 4700, 30 / 365, 0.17, put=True, rate=0.04)
        assert eg.implied_vol(price, 4780, 4700, 30 / 365, put=True, rate=0.04) == pytest.approx(0.17, abs=1e-6)

    def test_iv_nicht_bestimmbar(self):
        # Put-Preis unter dem inneren Wert -> keine Loesung
        assert eg.implied_vol(1.0, 90, 100, 0.1, put=True) is None
        assert eg.implied_vol(0, 100, 100, 0.1, put=True) is None
        assert eg.implied_vol(1.0, 100, 100, 0, put=True) is None


def test_restlaufzeit_bis_16_uhr_new_york():
    trade = datetime(2026, 10, 21, 13, 15, tzinfo=ET)
    assert eg.year_fraction(trade, date(2026, 10, 21)) == pytest.approx(2.75 / (365 * 24), rel=1e-9)


class TestIvrIvp:
    def test_berechnung(self):
        values = [10.0] * 10 + [30.0] * 10 + [20.0]   # Stichtag 20 zwischen Tief 10 und Hoch 30
        iv, ivr, ivp = eg.iv_rank_percentile(values)
        assert iv == 20.0
        assert ivr == pytest.approx(50.0)
        assert ivp == pytest.approx(50.0)               # 10 von 20 Vortagen lagen darunter

    def test_zu_wenig_tage(self):
        assert eg.iv_rank_percentile([0.2] * (eg.MIN_IV_DAYS - 1)) is None

    def test_leere_werte_werden_ignoriert(self):
        assert eg.iv_rank_percentile([0, None] + [0.2] * (eg.MIN_IV_DAYS - 1)) is None


@pytest.mark.parametrize("underlying, symbol, expected", [
    ("SPX", "SPXW  261021P07760000", ("index", "SPX", "CBOE")),
    ("SPX", "SPX   251121P05880000", ("index", "SPX", "CBOE")),
    ("", "NDXP  261120C21000000", ("index", "NDX", "NASDAQ")),
    ("TXN", "TXN   260717P00300000", ("stock", "TXN", "SMART")),
    ("", "KO    240809P00067000", ("stock", "KO", "SMART")),
])
def test_basiswert_zuordnung(underlying, symbol, expected):
    assert eg.underlying_spec(underlying, symbol) == expected


@pytest.mark.parametrize("row, expected", [
    ({"assetCategory": "OPT", "tradePrice": Decimal("3.73"), "status": None}, True),
    ({"assetCategory": "OPT", "tradePrice": Decimal("3.73"), "status": "Closed"}, True),
    ({"assetCategory": "OPT", "tradePrice": Decimal("0"), "status": "Expired"}, False),
    ({"assetCategory": "OPT", "tradePrice": Decimal("1.0"), "status": "Assigned"}, False),
    ({"assetCategory": "OPT", "tradePrice": Decimal("1.0"), "status": "CashSettled"}, False),
    ({"assetCategory": "STK", "tradePrice": Decimal("50"), "status": None}, False),
])
def test_auswahl_der_trades(row, expected):
    assert eg.is_candidate(row) is expected


class FakeSource:
    def __init__(self, price=None, ivs=()):
        self.price, self.ivs, self.calls = price, list(ivs), []

    def underlying_price(self, kind, usym, exch, when):
        self.calls.append(("price", kind, usym, when))
        return self.price

    def iv_values(self, kind, usym, exch, day):
        self.calls.append(("iv", kind, usym, day))
        return self.ivs


def _row(**over):
    row = {"tradeID": "T1", "symbol": "SPXW  261021P07760000", "underlyingSymbol": "SPX",
           "assetCategory": "OPT", "putCall": "P", "strike": Decimal("7760"),
           "expiry": datetime(2026, 10, 21), "dateTime": datetime(2026, 10, 21, 13, 15, 13),
           "tradePrice": Decimal("3.73"), "status": None}
    row.update(over)
    return row


def test_compute_greeks_mit_echtdaten_der_machbarkeitsprobe():
    """SPXW 0DTE aus der Probe vom 2026-10-29: Basis 7765,47 -> IV ~11 %, Delta ~-0,36."""
    src = FakeSource(price=7765.47, ivs=[0.10] * 100 + [0.20] * 100 + [0.13])
    res = eg.compute_greeks(_row(), src, ET, rate=0.04)
    assert res["error"] is None
    assert res["option_iv"] == pytest.approx(0.112, abs=0.002)
    assert res["delta"] == pytest.approx(-0.36, abs=0.01)
    assert res["ivr"] == pytest.approx(30.0)
    # Basiswert-Abfrage zur Ausfuehrungsminute, als Index SPX
    assert src.calls[0][:3] == ("price", "index", "SPX")
    assert src.calls[0][3] == datetime(2026, 10, 21, 13, 15, 13, tzinfo=ET)


def test_compute_greeks_ohne_daten_speichert_hinweis():
    res = eg.compute_greeks(_row(), FakeSource(price=None, ivs=[]), ET)
    assert res["delta"] is None and res["ivr"] is None
    assert "kein Basiswert-Kurs" in res["error"] and "zu wenig IV-Historie" in res["error"]


def test_ohne_tws_wird_uebersprungen(monkeypatch):
    """Nicht erreichbare TWS darf die Pipeline nicht stoppen: connect_tws() -> None, main() -> 0."""
    import ib_async

    def refuse(self, *a, **kw):
        raise ConnectionRefusedError("keine TWS")

    monkeypatch.setattr(ib_async.IB, "connect", refuse)
    monkeypatch.setattr(eg, "load_active_targets", lambda: [{"environment": "paper", "prefix": "x_"}])
    assert eg.connect_tws() is None
    assert eg.main([]) == 0


def test_verbindung_ist_schreibgeschuetzt(monkeypatch):
    import ib_async
    seen = {}

    def fake_connect(self, host, port, clientId, readonly, timeout):
        seen.update(host=host, port=port, clientId=clientId, readonly=readonly)

    monkeypatch.setattr(ib_async.IB, "connect", fake_connect)
    eg.connect_tws()
    assert seen["readonly"] is True
    assert seen["clientId"] == eg.TWS_CLIENT_ID
