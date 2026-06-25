import os
import tomllib
from sqlalchemy import create_engine, event
from dotenv import load_dotenv
from pathlib import Path

# Defines
MAX_TRADE_IDS = 3  # bei Aggregation: max. Anzahl der aufgeführten tradeID's
MAX_GAP_DAYS = 10  # Kampagnen: max. Tage in PENDING bevor CLOSED (empfohlen 7-14)

# Lade .env aus dem Projekt-Root
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

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
TABLE_PREFIX = os.getenv("TABLE_PREFIX", "")


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
TABLE_TRADES_SUMMARY = os.getenv("TABLE_TRADES_SUMMARY", "trades_summary")
TABLE_TRADES_OPEN = os.getenv("TABLE_TRADES_OPEN", "trades_open")
TABLE_TRADES_CLOSE = os.getenv("TABLE_TRADES_CLOSE", "trades_close")
TABLE_TRADES_FX = os.getenv("TABLE_TRADES_FX", "trades_fx")
TABLE_SYMBOLS = os.getenv("TABLE_SYMBOLS", "symbols")
TABLE_CAMPAIGN_LEDGER = os.getenv("TABLE_CAMPAIGN_LEDGER", "campaign_ledger")
TABLE_TRADING_CAMPAIGNS = os.getenv("TABLE_TRADING_CAMPAIGNS", "trading_campaigns")
TABLE_ACCOUNT_SNAPSHOTS = os.getenv("TABLE_ACCOUNT_SNAPSHOTS", "account_snapshots")

DEBUG_SQL = os.getenv("DEBUG_SQL", "false").lower() == "true"


# === Account-Mapping: IBKR accountId → User / Environment / Prefix ===

def _normalize_account_id(raw: str) -> str:
    """Letzte 4 Ziffern — maskiert ('U***9360') und unmaskiert ('U12369360') ergeben denselben Key."""
    digits = ''.join(filter(str.isdigit, raw))
    return digits[-4:]

# Key = letzte 4 Ziffern der IBKR accountId
# Beispiele: "U***65466" → "5466",  "U12368145" → "8145",  "DU***4049" → "4049"
ACCOUNT_MAP: dict[str, dict] = {
    "5466": {"user": "mike",   "table_prefix": "mike_",   "environment": "autom_money"},
    "9254": {"user": "mike",   "table_prefix": "mike_",   "environment": "autom_paper"},
    "9360": {"user": "mike",   "table_prefix": "mike_",   "environment": "money"},
    "4049": {"user": "mike",   "table_prefix": "mike_",   "environment": "paper"},
    "8145": {"user": "karola", "table_prefix": "karola_", "environment": "money"},
}

def get_account_config(raw_account_id: str) -> dict | None:
    """Gibt {user, table_prefix, environment} für eine accountId zurück (maskiert oder voll)."""
    return ACCOUNT_MAP.get(_normalize_account_id(raw_account_id))


# === Pipeline-Konfiguration ===

def load_active_targets() -> list[dict]:
    """
    Liest pipeline.toml und gibt alle aktiven Targets zurück.
    Format: [{"environment": str, "prefix": str}]
    Reihenfolge: Users in TOML-Reihenfolge, TEST zuletzt (nur wenn enabled=true).
    """
    toml_path = ROOT_DIR / "pipeline.toml"
    if not toml_path.exists():
        return []
    with open(toml_path, "rb") as f:
        cfg = tomllib.load(f)

    targets = []
    for user_name, user_cfg in cfg.get("users", {}).items():
        prefix = user_cfg["prefix"]
        for env in user_cfg.get("environments", []):
            targets.append({"environment": env, "prefix": prefix, "user": user_name})

    test_cfg = cfg.get("test", {})
    if test_cfg.get("enabled", False):
        targets.append({
            "environment": "test",
            "prefix": test_cfg.get("prefix", TABLE_PREFIX),
            "user": "test",
        })

    return targets


def is_environment_active(environment: str, prefix: str) -> bool:
    """Prüft ob (environment, prefix) in pipeline.toml als aktiv konfiguriert ist."""
    return any(
        t["environment"] == environment and t["prefix"] == prefix
        for t in load_active_targets()
    )
