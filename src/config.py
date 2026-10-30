import os
import tomllib
from functools import lru_cache
from sqlalchemy import create_engine, event
from dotenv import load_dotenv
from pathlib import Path

# Defines
MAX_TRADE_IDS = 3  # bei Aggregation: max. Anzahl der aufgeführten tradeID's

# Lade .env aus dem Projekt-Root
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def read_positive_int_env(name: str, default: int) -> int:
    """Ganzzahl >= 1 aus der .env; fehlt der Eintrag oder ist er leer, gilt der Default.
    Ein ungültiger Wert bricht ab, statt still mit dem Default weiterzurechnen."""
    raw = os.getenv(name, "").strip()
    if raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name}={raw!r} in .env ist keine ganze Zahl") from None
    if value < 1:
        raise ValueError(f"{name}={value} in .env muss mindestens 1 sein")
    return value


# Kampagnen: Tage in PENDING ohne neuen Trade, bevor die Kampagne CLOSED wird (empfohlen 7-14).
# Wirkt nur auf künftige Verarbeitung — bestehende Kampagnen erst nach einem Neuaufbau.
MAX_GAP_DAYS = read_positive_int_env("MAX_GAP_DAYS", 10)

# Pipeline-Schritt "enrich" (src/enrich_greeks.py): Delta/IV/IVR/IVP über die TWS-API.
# Verbindung nur lesend; eigene clientId, damit andere TWS-Anwendungen nicht gestört werden.
TWS_HOST = os.getenv("TWS_HOST", "127.0.0.1").strip() or "127.0.0.1"
TWS_PORT = read_positive_int_env("TWS_PORT", 7497)          # 7497 = Papierkonto, 7496 = Echtgeld
TWS_CLIENT_ID = read_positive_int_env("TWS_CLIENT_ID", 630)
GREEKS_RATE = float(os.getenv("GREEKS_RATE", "0.04").strip() or "0.04")   # risikofreier Zins (Näherung)
# Zeitzone der dateTime-Werte aus der Flex Query (IBKR-Standard: New York)
GREEKS_TRADE_TZ = os.getenv("GREEKS_TRADE_TZ", "America/New_York").strip() or "America/New_York"


# === Ablageordner für IBKR-Berichte ===
# Definiert in src/utils/data_dirs.py (schlank, auch für den Minimal-Abruf-Client) und hier nur
# durchgereicht: TRADE_XML_DIR / TRADE_CSV_DIR per .env, sonst C:\Trade_XML / C:\Trade_CSV
# (Windows) bzw. ~/Trade_XML / ~/Trade_CSV (Linux/macOS).
from src.utils.data_dirs import (  # noqa: E402
    TRADE_XML_DIR, TRADE_CSV_DIR, XML_INCOMING_MAIL, XML_INCOMING_API, CSV_INCOMING,
)


# === Zentrale User-Registry (users.toml) ===
# Einzige Quelle fuer den Zusammenhang User <-> Tabellen-Prefix. Wie accounts.toml und
# pipeline.toml lokal und nicht versioniert (enthaelt die echten Benutzernamen) — Vorlage:
# users.toml.example.

@lru_cache(maxsize=1)
def load_users() -> dict[str, str]:
    """Liest users.toml: {user_name: table_prefix}. Leeres Dict falls Datei fehlt."""
    toml_path = ROOT_DIR / "users.toml"
    if not toml_path.exists():
        return {}
    with open(toml_path, "rb") as f:
        cfg = tomllib.load(f)
    return {name: data["prefix"] for name, data in cfg.items()}


def _registered_prefix(user_name: str, source: str) -> str:
    """Prefix eines Users aus users.toml. Fehlt der User, Abbruch statt leerem Prefix —
    sonst landen die Daten unbemerkt in Tabellen ohne Prefix (z.B. trades_raw)."""
    users = load_users()
    if user_name not in users:
        raise ValueError(
            f"Benutzer '{user_name}' aus {source} fehlt in users.toml — dort eintragen "
            f"(Vorlage: users.toml.example, z.B. [{user_name}] prefix = \"{user_name}_\")."
        )
    return users[user_name]


# === DB Basis-Konfiguration ===
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", 3306))

# --- Mapping Umgebungen <-> Datenbanken ---
DB_MAP = {
    "money": os.getenv("DB_NAME_MONEY", "ibkr_money"),
    "paper": os.getenv("DB_NAME_PAPER", "ibkr_paper"),
    "test": os.getenv("DB_NAME_TEST", "ibkr_test"),  # gleiche DB wie paper
    "autom_money": os.getenv("DB_NAME_AUTOM_MONEY", "ibkr_autom_money"),
    "autom_paper": os.getenv("DB_NAME_AUTOM_PAPER", "ibkr_autom_paper")
}

# OPTIONALER TABLE-PREFIX (z.B. "mike_")
# Direkt per TABLE_PREFIX setzen (Altbestand, z.B. Server-.env) ODER per DEFAULT_USER=<name>
# (Prefix wird dann aus users.toml aufgeloest) — TABLE_PREFIX gewinnt, falls beides gesetzt ist.
TABLE_PREFIX = os.getenv("TABLE_PREFIX", "")
if not TABLE_PREFIX:
    TABLE_PREFIX = load_users().get(os.getenv("DEFAULT_USER", ""), "")


def get_db_url(env: str) -> str:
    """Gibt die DB-URL für das gewünschte Environment zurück"""
    if env not in DB_MAP:
        raise ValueError(f"Unbekanntes Environment '{env}', erlaubt: {list(DB_MAP.keys())}")
    db_name = DB_MAP[env]
    return f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{db_name}"


def get_engine(env: str):
    """Gibt eine SQLAlchemy-Engine für das gewünschte Environment zurück"""
    engine = create_engine(get_db_url(env))

    "MySQL unter Win11 ist scheinbar strikter als unter Win10 -> damit es kompatibel bleibt (dateTime dürfen None sein)"
    @event.listens_for(engine, "connect")
    def set_mysql_mode(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("SET SESSION sql_mode='NO_ZERO_IN_DATE,NO_ZERO_DATE,NO_ENGINE_SUBSTITUTION'")
        cursor.close()

    return engine


# === Tabellen-Namen ===
TABLE_TRADES_RAW = os.getenv("TABLE_TRADES_RAW", "trades_raw")
TABLE_TRADES_OPEN = os.getenv("TABLE_TRADES_OPEN", "trades_open")
TABLE_TRADES_CLOSE = os.getenv("TABLE_TRADES_CLOSE", "trades_close")
TABLE_TRADES_FX = os.getenv("TABLE_TRADES_FX", "trades_fx")
TABLE_SYMBOLS = os.getenv("TABLE_SYMBOLS", "symbols")
TABLE_CAMPAIGN_LEDGER = os.getenv("TABLE_CAMPAIGN_LEDGER", "campaign_ledger")
TABLE_TRADING_CAMPAIGNS = os.getenv("TABLE_TRADING_CAMPAIGNS", "trading_campaigns")
TABLE_ACCOUNT_SNAPSHOTS = os.getenv("TABLE_ACCOUNT_SNAPSHOTS", "account_snapshots")
TABLE_TRADE_PLANNER = os.getenv("TABLE_TRADE_PLANNER", "trade_planner")
TABLE_TRADE_GREEKS = os.getenv("TABLE_TRADE_GREEKS", "trade_greeks")   # abgeleitet (enrich), nicht in reset_IBKR_DB
TABLE_IV_HISTORY = os.getenv("TABLE_IV_HISTORY", "iv_history")         # abgeleitet (enrich), nicht in reset_IBKR_DB
TABLE_PSYCHOLOGY_RULESETS   = os.getenv("TABLE_PSYCHOLOGY_RULESETS",   "psychology_rulesets")
TABLE_PSYCHOLOGY_RULES      = os.getenv("TABLE_PSYCHOLOGY_RULES",      "psychology_rules")
TABLE_PSYCHOLOGY_ENTRIES    = os.getenv("TABLE_PSYCHOLOGY_ENTRIES",    "psychology_entries")
TABLE_PSYCHOLOGY_COMPLIANCE = os.getenv("TABLE_PSYCHOLOGY_COMPLIANCE", "psychology_compliance_results")

DEBUG_SQL = os.getenv("DEBUG_SQL", "false").lower() == "true"


# === Account-Mapping: IBKR accountId → User / Environment / Prefix ===
# Liegt in accounts.toml (wie pipeline.toml maschinen-/personenspezifisch, nicht
# versioniert) — enthaelt reale IBKR-Kontodaten, siehe accounts.toml.example fuer
# das Format. Tabellen-Prefix steht dort bewusst nicht mit drin — kommt zur Laufzeit
# aus users.toml (siehe get_account_config), damit Prefixe nur an einer Stelle stehen.

@lru_cache(maxsize=1)
def load_account_map() -> dict[str, dict]:
    """Liest accounts.toml: {letzte 4 Ziffern der accountId: {user, environment}}. Leeres Dict falls Datei fehlt."""
    toml_path = ROOT_DIR / "accounts.toml"
    if not toml_path.exists():
        return {}
    with open(toml_path, "rb") as f:
        return tomllib.load(f)


def _normalize_account_id(raw: str) -> str:
    """Letzte 4 Ziffern — maskierte und unmaskierte accountId ergeben denselben Key."""
    digits = ''.join(filter(str.isdigit, raw))
    return digits[-4:]


def get_account_config(raw_account_id: str) -> dict | None:
    """Gibt {user, table_prefix, environment} für eine accountId zurück (maskiert oder voll)."""
    entry = load_account_map().get(_normalize_account_id(raw_account_id))
    if entry is None:
        return None
    return {
        "user": entry["user"],
        "table_prefix": _registered_prefix(entry["user"], "accounts.toml"),
        "environment": entry["environment"],
    }


# === Pipeline-Konfiguration ===

def load_active_targets() -> list[dict]:
    """
    Liest pipeline.toml und gibt alle aktiven Targets zurück.
    Format: [{"environment": str, "prefix": str, "user": str}]
    Reihenfolge: Users in TOML-Reihenfolge, TEST-Einträge ([[test]]) zuletzt.
    Ein [[test]]-Eintrag ist immer aktiv — kein enabled-Schalter, zum Deaktivieren
    den Eintrag aus der TOML entfernen.

    Tabellen-Prefix: ein explizites "prefix"-Feld in pipeline.toml gewinnt (Override,
    z.B. fuer einen User ohne users.toml-Eintrag); ohne "prefix"-Feld wird der User-Name
    (TOML-Sektion bzw. "user"-Feld beim Test-Eintrag) in users.toml nachgeschlagen.
    """
    toml_path = ROOT_DIR / "pipeline.toml"
    if not toml_path.exists():
        return []
    with open(toml_path, "rb") as f:
        cfg = tomllib.load(f)

    targets = []
    for user_name, user_cfg in cfg.get("users", {}).items():
        prefix = user_cfg.get("prefix") or _registered_prefix(user_name, "pipeline.toml")
        for env in user_cfg.get("environments", []):
            targets.append({"environment": env, "prefix": prefix, "user": user_name})

    for test_cfg in cfg.get("test", []):
        test_user = test_cfg.get("user", "test")
        prefix = test_cfg.get("prefix") or _registered_prefix(test_user, "pipeline.toml [[test]]")
        targets.append({
            "environment": "test",
            "prefix": prefix,
            "user": test_user,
        })

    return targets


def is_environment_active(environment: str, prefix: str) -> bool:
    """Prüft ob (environment, prefix) in pipeline.toml als aktiv konfiguriert ist."""
    return any(
        t["environment"] == environment and t["prefix"] == prefix
        for t in load_active_targets()
    )
