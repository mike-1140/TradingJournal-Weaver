"""Zahlenwerte aus der .env (z.B. MAX_GAP_DAYS): Default bei fehlendem Eintrag,
Abbruch bei ungültigem Wert statt stillem Weiterrechnen mit dem Default."""
import pytest

from src import config


def test_fehlender_eintrag_liefert_default(monkeypatch):
    monkeypatch.delenv("MAX_GAP_DAYS", raising=False)
    assert config.read_positive_int_env("MAX_GAP_DAYS", 10) == 10


def test_leerer_eintrag_liefert_default(monkeypatch):
    monkeypatch.setenv("MAX_GAP_DAYS", "  ")
    assert config.read_positive_int_env("MAX_GAP_DAYS", 10) == 10


def test_gesetzter_wert_wird_uebernommen(monkeypatch):
    monkeypatch.setenv("MAX_GAP_DAYS", "14")
    assert config.read_positive_int_env("MAX_GAP_DAYS", 10) == 14


@pytest.mark.parametrize("raw", ["zehn", "7.5", "0", "-3"])
def test_ungueltiger_wert_bricht_ab(monkeypatch, raw):
    monkeypatch.setenv("MAX_GAP_DAYS", raw)
    with pytest.raises(ValueError, match="MAX_GAP_DAYS"):
        config.read_positive_int_env("MAX_GAP_DAYS", 10)


def test_inventory_tracker_nutzt_den_konfigurierten_wert():
    # Der Tracker übernimmt MAX_GAP_DAYS aus config als Default — kein eigener fester Wert
    import inspect
    from src.parsers.inventory_tracker import InventoryTracker

    default = inspect.signature(InventoryTracker.__init__).parameters["max_gap_days"].default
    assert default == config.MAX_GAP_DAYS
