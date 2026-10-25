# src/utils/data_dirs.py
"""
Ablageordner für die IBKR-Berichte (XML/CSV), per .env einstellbar.

Bewusst ohne schwere Abhängigkeiten (nur os, pathlib, python-dotenv): die Abruf-Skripte
get_flexquery_emails.py / get_flexquery_api.py importieren dieses Modul und laufen auch auf
einem Minimal-Client, der nur python-dotenv und requests installiert hat (siehe Technik-Handbuch
„Verteilter Abruf“). Hier daher nie sqlalchemy, pandas o. Ä. importieren.

Ohne Eintrag in der .env gelten C:\\Trade_XML / C:\\Trade_CSV (Windows, bisheriges Verhalten)
bzw. ~/Trade_XML / ~/Trade_CSV (Linux/macOS).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

from src.utils.path_utils import get_project_root

load_dotenv(get_project_root() / ".env")


def default_data_dir(name: str, windows: bool | None = None) -> Path:
    """Standard-Ablageordner: unter Windows C:\\<name> (bisheriges Verhalten),
    unter Linux/macOS ~/<name> im Benutzerordner."""
    if windows is None:
        windows = os.name == "nt"
    return Path(f"C:\\{name}") if windows else Path.home() / name


def read_dir_env(name: str, default: Path) -> Path:
    """Ordner aus der .env (~ und %VAR%/$VAR werden aufgelöst); leer oder fehlend -> default."""
    raw = os.getenv(name, "").strip()
    if raw == "":
        return default
    return Path(os.path.expandvars(os.path.expanduser(raw)))


# Alle Unterordner (<environment>\<benutzer>\processed, summary_*.xml) werden davon abgeleitet.
TRADE_XML_DIR = read_dir_env("TRADE_XML_DIR", default_data_dir("Trade_XML"))
TRADE_CSV_DIR = read_dir_env("TRADE_CSV_DIR", default_data_dir("Trade_CSV"))
XML_INCOMING_MAIL = TRADE_XML_DIR / "incoming_mail"   # get_flexquery_emails.py
XML_INCOMING_API = TRADE_XML_DIR / "incoming_api"     # get_flexquery_api.py
CSV_INCOMING = TRADE_CSV_DIR / "incoming"             # Kontoauszüge (Activity Statement CSV)
