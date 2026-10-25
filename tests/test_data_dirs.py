"""Ablageordner für IBKR-Berichte (src/utils/data_dirs.py): Standard je Betriebssystem,
Überschreiben per .env, einheitliche Nutzung in allen Skripten — und die Abruf-Skripte bleiben
ohne schwere Abhängigkeiten (Minimal-Client hat nur python-dotenv + requests)."""
import subprocess
import sys
from pathlib import Path

from src import config
from src.utils import data_dirs
from src.utils.path_utils import get_project_root


def test_standard_unter_windows_ist_laufwerk_c():
    assert data_dirs.default_data_dir("Trade_XML", windows=True) == Path(r"C:\Trade_XML")


def test_standard_unter_linux_und_macos_ist_der_benutzerordner():
    assert data_dirs.default_data_dir("Trade_CSV", windows=False) == Path.home() / "Trade_CSV"


def test_fehlender_oder_leerer_eintrag_liefert_den_standard(monkeypatch):
    default = Path("/standard")
    monkeypatch.delenv("TRADE_XML_DIR", raising=False)
    assert data_dirs.read_dir_env("TRADE_XML_DIR", default) == default
    monkeypatch.setenv("TRADE_XML_DIR", "   ")
    assert data_dirs.read_dir_env("TRADE_XML_DIR", default) == default


def test_gesetzter_ordner_wird_uebernommen_und_tilde_aufgeloest(monkeypatch):
    monkeypatch.setenv("TRADE_XML_DIR", "~/Berichte/xml")
    assert data_dirs.read_dir_env("TRADE_XML_DIR", Path("/standard")) == Path.home() / "Berichte" / "xml"


def test_unterordner_haengen_am_basisordner():
    assert data_dirs.XML_INCOMING_MAIL == data_dirs.TRADE_XML_DIR / "incoming_mail"
    assert data_dirs.XML_INCOMING_API == data_dirs.TRADE_XML_DIR / "incoming_api"
    assert data_dirs.CSV_INCOMING == data_dirs.TRADE_CSV_DIR / "incoming"


def test_alle_skripte_nutzen_dieselben_ordner():
    from src import get_flexquery_api, get_flexquery_emails, import_csv_snapshots, import_ibkr_trades, xml_append_summary

    assert config.TRADE_XML_DIR == data_dirs.TRADE_XML_DIR
    assert get_flexquery_api.OUT_FOLDER_XML_API == str(data_dirs.XML_INCOMING_API)
    assert get_flexquery_emails.IN_FOLDER_XML_INCOMING == str(data_dirs.XML_INCOMING_MAIL)
    assert get_flexquery_emails.IN_FOLDER_CSV_INCOMING == str(data_dirs.CSV_INCOMING)
    assert import_csv_snapshots.IN_FOLDER_CSV_INCOMING == data_dirs.CSV_INCOMING
    assert import_ibkr_trades.BASE_XML_INCOMING_MAIL == str(data_dirs.XML_INCOMING_MAIL)
    assert import_ibkr_trades.BASE_XML_INCOMING_API == str(data_dirs.XML_INCOMING_API)
    assert import_ibkr_trades.BASE_CSV_INCOMING == str(data_dirs.CSV_INCOMING)
    assert import_ibkr_trades.BASE_XML_FILE_PATH_PROD == str(data_dirs.TRADE_XML_DIR)
    assert xml_append_summary.BASE_XML_FILE_PATH_PROD == str(data_dirs.TRADE_XML_DIR)


def test_abruf_skripte_laden_keine_schweren_pakete():
    # Eigener Prozess, damit bereits geladene Module aus anderen Tests nicht mitzählen
    code = (
        "import sys, src.get_flexquery_emails, src.get_flexquery_api; "
        "print(','.join(m for m in ('sqlalchemy', 'pandas', 'numpy', 'pymysql') if m in sys.modules))"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=get_project_root(),
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "", f"Abruf-Skripte laden: {result.stdout.strip()}"
