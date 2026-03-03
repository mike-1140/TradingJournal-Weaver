import os
import pandas as pd
import pytest
from src.import_ibkr_trades import load_flex_xml, process_flexquery, handle_booktrades

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

@pytest.mark.parametrize("xml_file,expected_counts", [
    ("flex_assigned.xml", {"trades": 1, "eae": 1, "ca": 0, "cashfx": 0}),
    ("flex_expired.xml", {"trades": 1, "eae": 1, "ca": 0, "cashfx": 0}),
    ("flex_cashsettlement.xml", {"trades": 1, "eae": 2, "ca": 0, "cashfx": 0}),
    ("flex_fx.xml", {"trades": 0, "eae": 0, "ca": 0, "cashfx": 1}),
    ("flex_corporateaction.xml", {"trades": 0, "eae": 0, "ca": 1, "cashfx": 0}),
])
def test_load_flex_xml_counts(xml_file, expected_counts):
    xml_path = os.path.join(DATA_DIR, xml_file)
    df_trades, df_eae, df_ca, df_cashfx = load_flex_xml(xml_path)
    assert len(df_trades) == expected_counts["trades"]
    assert len(df_eae) == expected_counts["eae"]
    assert len(df_ca) == expected_counts["ca"]
    assert len(df_cashfx) == expected_counts["cashfx"]

def test_handle_booktrades_assignment():
    xml_path = os.path.join(DATA_DIR, "flex_assigned.xml")
    df_trades, df_eae, _, _ = load_flex_xml(xml_path)
    result = handle_booktrades(df_trades, df_eae, "tradeDate", "tradeDate")
    assert "Assigned" in result["status"].values

def test_handle_booktrades_expired():
    xml_path = os.path.join(DATA_DIR, "flex_expired.xml")
    df_trades, df_eae, _, _ = load_flex_xml(xml_path)
    result = handle_booktrades(df_trades, df_eae, "tradeDate", "tradeDate")
    assert "Expired" in result["status"].values

def test_handle_booktrades_cashsettled():
    xml_path = os.path.join(DATA_DIR, "flex_cashsettlement.xml")
    df_trades, df_eae, _, _ = load_flex_xml(xml_path)
    result = handle_booktrades(df_trades, df_eae, "tradeDate", "tradeDate")
    assert "CashSettled" in result["status"].values

def test_process_flexquery_with_corporate_action():
    xml_path = os.path.join(DATA_DIR, "flex_corporateaction.xml")
    df_trades, df_eae, df_ca, df_cashfx = load_flex_xml(xml_path)
    df_out = process_flexquery(df_trades, df_eae, df_ca, xml_path)
    assert any(df_out["is_split"]), "Corporate action (split) should be detected"

def test_process_flexquery_fx():
    xml_path = os.path.join(DATA_DIR, "flex_fx.xml")
    _, _, _, df_cashfx = load_flex_xml(xml_path)
    assert "fxRate" in df_cashfx.columns
    assert df_cashfx.loc[0, "baseCurrency"] == "EUR"
    assert df_cashfx.loc[0, "quoteCurrency"] == "USD"
