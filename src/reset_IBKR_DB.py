# src/reset_DB.py

import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
from datetime import datetime

from src.config import DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_MAP, TABLE_PREFIX, get_db_url
from src.logger_setup import setup_logging
from src.utils.path_utils import get_project_root


def apply_table_prefix(sql_text: str, table_prefix: str) -> str:
    """
    Ersetzt Platzhalter __PREFIX__ durch tatsächlichen Table Prefix.
    Falls kein Prefix gesetzt, bleibt SQL unverändert.
    """
    if table_prefix:
        return sql_text.replace("__PREFIX__", table_prefix)
    else:
        return sql_text.replace("__PREFIX__", "")  # Entfernen, falls leer


def process_setup_data(environment: str, table_prefix: str) -> str:
    environment = environment.lower()
    env_up = environment.upper()

    if environment not in DB_MAP:
        raise ValueError(f"Unbekanntes Environment '{environment}'. Erlaubt sind: {list(DB_MAP.keys())}")

    db_name = DB_MAP[environment]

    # Logging
    log_file = get_project_root() / "log/app.log"
    logger, _ = setup_logging('my_app', level="simple", log_file=log_file)
    logger.info("=" * 80)
    logger.info(f"---- Datenbankinitialisierung (" + datetime.now().strftime('%Y-%m-%d - %H:%M:%S') + ")")
    logger.info("=" * 80)
    logger.info(f"Environment: {env_up}, Präfix: '{table_prefix}'")

    # Verbindung zur MySQL-Instanz (ohne DB)
    server_url = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}"
    engine = create_engine(server_url)

    # Prüfen ob DB existiert, sonst erstellen
    with engine.connect() as conn:
        existing_dbs = [row[0] for row in conn.execute(text("SHOW DATABASES")).fetchall()]
        if db_name in existing_dbs:
            logger.info(f"Datenbank '{db_name}' existiert bereits")
            # print(f"Datenbank '{db_name}' existiert bereits.")
        else:
            logger.info(f"Datenbank '{db_name}' wird erstellt...")
            # print(f"Datenbank '{db_name}' wird erstellt...")
            conn.execute(text(f"CREATE DATABASE {db_name}"))

    # Neue Verbindung mit konkreter Datenbank
    db_url = get_db_url(environment)
    db_engine = create_engine(db_url)

    # SQL-Dateien einlesen und ausführen
    processed_files = []
    SQL_PATH = get_project_root() / "sql"
    sql_files = [
        'trades_raw',
        'trade_tag_pivot',
        'trade_notes',
        'trades_open',
        'trades_close',
        'trades_fx',
        'symbols',
        'trading_campaigns',
        'campaign_ledger'
    ]

    with db_engine.connect() as conn:
        for sql_file in sql_files:
            file_path = SQL_PATH / f"{sql_file}.sql"
            if not file_path.exists():
                print(f"SQL-Datei {file_path} nicht gefunden, überspringe.")
                continue

            with open(file_path, "r", encoding="utf-8") as f:
                raw_sql = f.read()

            # ersetze __PREFIX__ mit dem tatsächlichen Präfix
            sql_with_prefix = apply_table_prefix(raw_sql, table_prefix)

            commands = sql_with_prefix.split(";")
            for cmd in commands:
                cmd = cmd.strip()
                if cmd:
                    try:
                        conn.execute(text(cmd))
                    except ProgrammingError as e:
                        print(f"Fehler in Datei '{sql_file}.sql': {e}")

            processed_files.append(sql_file)
    logger.info("Verarbeitete SQL-Dateien: %s",
                ", ".join(processed_files)
                )
    logger.info(f"Setup/Initialisierung abgeschlossen")
    # print(f"Setup für Environment '{environment}' abgeschlossen.")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Bitte Environment angeben: money | paper | test | autom_money | autom_paper")
        print("Optional: Table-Prefix, z.B.: python reset_IBKR_DB.py money mike_")
        sys.exit(1)

    # --- OPTIONALER TABLE PREFIX ÜBER COMMANDLINE ---
    if len(sys.argv) >= 3:
        table_prefix = sys.argv[2]
        print(f"*** TABLE PREFIX via Commandline aktiv: '{table_prefix}' ***")
    else:
        table_prefix = TABLE_PREFIX
        print("*** Table-Prefix aus Environment gesetzt ***")

    env = sys.argv[1].lower()
    process_setup_data(env, table_prefix)
