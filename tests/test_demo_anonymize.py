# Regressionstest: Test-Quellen mit Options-Symbolen in einfacher Schreibweise fuehrten in der Demo zu
# doppelten Trades, weil die Checksum das Symbol enthaelt.

import xml.etree.ElementTree as ET

from tools.demo.anonymize_demo_source import anonymize_file, normalize_option_symbol


def test_einfaches_leerzeichen_wird_aufgefuellt():
    assert normalize_option_symbol("ON 251114P00043500") == "ON    251114P00043500"
    assert normalize_option_symbol("SPY 251107C00671000") == "SPY   251107C00671000"


def test_ibkr_schreibweise_und_aktien_bleiben():
    assert normalize_option_symbol("ON    251114P00043500") == "ON    251114P00043500"
    assert normalize_option_symbol("OMEX") == "OMEX"
    assert normalize_option_symbol("OMEX.OLD") == "OMEX.OLD"
    assert normalize_option_symbol("") == ""


def test_datei_wird_vereinheitlicht_und_anonymisiert(tmp_path):
    src = tmp_path / "in.xml"
    src.write_text(
        '<FlexQueryResponse><FlexStatements><FlexStatement accountId="U1">'
        '<Trades><Trade accountId="U1" symbol="ON 251114P00043500" underlyingSymbol="ON"/></Trades>'
        "</FlexStatement></FlexStatements></FlexQueryResponse>"
    )
    dest = tmp_path / "out.xml"

    anonymize_file(src, dest)

    trade = next(ET.parse(dest).getroot().iter("Trade"))
    assert trade.get("symbol") == "ON    251114P00043500"
    assert trade.get("accountId") != "U1"
