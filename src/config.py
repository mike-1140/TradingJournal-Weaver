import os
import tomllib
from functools import lru_cache
from sqlalchemy import create_engine, event
from dotenv import load_dotenv
from pathlib import Path

# Defines
MAX_TRADE_IDS = 3  # bei Aggregation: max. Anzahl der aufgeführten tradeID's
MAX_GAP_DAYS = 10  # Kampagnen: max. Tage in PENDING bevor CLOSED (empfohlen 7-14)

# Lade .env aus dem Projekt-Root
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


# === Zentrale User-Registry (users.toml) ===
# Einzige Quelle fuer den Zusammenhang User <-> Tabellen-Prefix. Im Gegensatz zu
# pipeline.toml gilt users.toml teamweit und ist versioniert (kein .gitignore).

@lru_cache(maxsize=1)
def load_users() -> dict[str, str]:
    """Liest users.toml: {user_name: table_prefix}. Leeres Dict falls Datei fehlt."""
    toml_path = ROOT_DIR / "users.toml"
    if not toml_path.exists():
        return {}
    with open(toml_path, "rb") as f:
        cfg = tomllib.load(f)
    return {name: data["prefix"] for name, data in cfg.items()}


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
TABLE_PSYCHOLOGY_RULESETS   = os.getenv("TABLE_PSYCHOLOGY_RULESETS",   "psychology_rulesets")
TABLE_PSYCHOLOGY_RULES      = os.getenv("TABLE_PSYCHOLOGY_RULES",      "psychology_rules")
TABLE_PSYCHOLOGY_ENTRIES    = os.getenv("TABLE_PSYCHOLOGY_ENTRIES",    "psychology_entries")
TABLE_PSYCHOLOGY_COMPLIANCE = os.getenv("TABLE_PSYCHOLOGY_COMPLIANCE", "psychology_compliance_results")

DEBUG_SQL = os.getenv("DEBUG_SQL", "false").lower() == "true"


# === Account-Mapping: IBKR accountId → User / Environment / Prefix ===

def _normalize_account_id(raw: str) -> str:
    """Letzte 4 Ziffern — maskiert ('U***9360') und unmaskiert ('U12369360') ergeben denselben Key."""
    digits = ''.join(filter(str.isdigit, raw))
    return digits[-4:]

# Key = letzte 4 Ziffern der IBKR accountId
# Beispiele: "U***65466" → "5466",  "U12368145" → "8145",  "DU***4049" → "4049"
# Tabellen-Prefix steht bewusst NICHT hier — kommt zur Laufzeit aus users.toml (siehe
# get_account_config), damit "mike_"/"karola_" nur an einer Stelle im Projekt steht.
ACCOUNT_MAP: dict[str, dict] = {
    "5466": {"user": "mike",   "environment": "autom_money"},
    "9254": {"user": "mike",   "environment": "autom_paper"},
    "9360": {"user": "mike",   "environment": "money"},
    "4049": {"user": "mike",   "environment": "paper"},
    "8145": {"user": "karola", "environment": "money"},
}

def get_account_config(raw_account_id: str) -> dict | None:
    """Gibt {user, table_prefix, environment} für eine accountId zurück (maskiert oder voll)."""
    entry = ACCOUNT_MAP.get(_normalize_account_id(raw_account_id))
    if entry is None:
        return None
    return {
        "user": entry["user"],
        "table_prefix": load_users().get(entry["user"], ""),
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

    users = load_users()
    targets = []
    for user_name, user_cfg in cfg.get("users", {}).items():
        prefix = user_cfg.get("prefix") or users.get(user_name, TABLE_PREFIX)
        for env in user_cfg.get("environments", []):
            targets.append({"environment": env, "prefix": prefix, "user": user_name})

    for test_cfg in cfg.get("test", []):
        test_user = test_cfg.get("user", "test")
        prefix = test_cfg.get("prefix") or users.get(test_user, TABLE_PREFIX)
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
