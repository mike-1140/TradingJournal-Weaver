# Tests fuer find_out_of_order_trades() -- Warnung bei Trades in falscher Reihenfolge
# (Roadmap, umgesetzt 2026-10-28). Ein neu importierter Trade, der zeitlich vor dem juengsten
# bereits verarbeiteten liegt (z. B. nachgeholter alter Bericht), wuerde gegen den aktuellen
# Stand laufen -- process_trades() haelt das Environment dann an.

from datetime import datetime

import pandas as pd

from src.process_ibkr_trades import find_out_of_order_trades

LAST = datetime(2025, 9, 19, 16, 20)


def _df(*rows):
    return pd.DataFrame([{"assetCategory": a, "status": s, "dateTime": dt, "symbol": sym}
                         for a, s, dt, sym in rows])


def test_nur_neuere_trades_sind_in_ordnung():
    df = _df(("STK", None, datetime(2025, 9, 22, 10, 0), "ABC"))
    blocking, tolerated = find_out_of_order_trades(df, LAST)
    assert blocking.empty and tolerated.empty


def test_gleicher_zeitpunkt_ist_erlaubt():
    df = _df(("STK", None, LAST, "ABC"))
    blocking, tolerated = find_out_of_order_trades(df, LAST)
    assert blocking.empty and tolerated.empty


def test_aelterer_aktien_trade_blockiert():
    df = _df(("STK", None, datetime(2025, 9, 10, 10, 0), "ABC"),
             ("STK", None, datetime(2025, 9, 22, 10, 0), "XYZ"))
    blocking, tolerated = find_out_of_order_trades(df, LAST)
    assert list(blocking["symbol"]) == ["ABC"]
    assert tolerated.empty


def test_verspaeteter_options_verfall_blockiert_nicht():
    """Echtdaten-Muster: SPY-Puts mit Verfall 18.09. kamen erst nach einem Eintrag vom 19.09."""
    df = _df(("OPT", "Expired", datetime(2025, 9, 18, 16, 20), "SPY P654"),
             ("OPT", "Assigned", datetime(2025, 9, 18, 16, 20), "SPY P650"),
             ("OPT", "CashSettled", datetime(2025, 9, 18, 16, 20), "SPXW P6500"))
    blocking, tolerated = find_out_of_order_trades(df, LAST)
    assert blocking.empty
    assert len(tolerated) == 3


def test_verspaetete_aktie_aus_zuteilung_blockiert():
    """Die Aktie aus einer Zuteilung bleibt geprueft -- sonst entsteht z. B. ein Verkauf ohne Bestand."""
    df = _df(("STK", None, datetime(2025, 9, 18, 16, 20), "SPY"))
    blocking, _ = find_out_of_order_trades(df, LAST)
    assert len(blocking) == 1


def test_normale_option_und_cash():
    df = _df(("OPT", "Closed", datetime(2025, 9, 10, 10, 0), "SPY C700"),  # normaler Trade -> blockiert
             ("CASH", None, datetime(2025, 9, 10, 10, 0), "EUR.USD"))      # CASH nie geprueft
    blocking, tolerated = find_out_of_order_trades(df, LAST)
    assert list(blocking["symbol"]) == ["SPY C700"]
    assert tolerated.empty


def test_ohne_verarbeitete_trades_keine_pruefung():
    df = _df(("STK", None, datetime(2020, 1, 1), "ABC"))
    blocking, tolerated = find_out_of_order_trades(df, None)
    assert blocking.empty and tolerated.empty
