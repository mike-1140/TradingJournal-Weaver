# src/db/db_access.py

from contextlib import contextmanager
from typing import Any, Type, List, Dict, Optional, Literal
import pandas as pd
from sqlalchemy import text, inspect
from src.config import (
    get_engine,
    DB_MAP,
    TABLE_PREFIX,
    TABLE_TRADES_RAW,
    TABLE_TRADES_OPEN,
    TABLE_TRADES_FX,
    TABLE_SYMBOLS,
    TABLE_TRADE_NOTES,
    TABLE_TRADE_TAG_PIVOT,
    TABLE_TRADING_CAMPAIGNS,
    DEBUG_SQL
)
from src.trade_schemas import OpenTradeSchema, BaseSchema, ClosedTradeSchema


# ============================================================
# Low-Level DB Access
# ============================================================

class DBAccess:
    def __init__(self, logger, environment: str = "paper", table_prefix: Optional[str] = None):
        if environment not in DB_MAP:
            raise ValueError(
                f"Unbekanntes Environment '{environment}', erlaubt: {list(DB_MAP.keys())}"
            )

        self.env = environment
        self.engine = get_engine(environment)
        self.table_prefix = table_prefix or TABLE_PREFIX
        self.db_logger = logger
        self._conn = None  # aktive Transaktions-Connection (None = kein aktiver TX)

    def _prefixed(self, table_name: str) -> str:
        return f"{self.table_prefix}{table_name}" if self.table_prefix else table_name

    # ------------------------
    # Logger helpers
    # ------------------------

    def _log_sql(self, sql: str, params: dict | list | None, force: bool = False):
        if not (DEBUG_SQL or force):
            return
        self.db_logger.info(self._format_sql_for_log(sql, params))

    @staticmethod
    def _format_sql_for_log(sql: str, params: dict | None = None) -> str:
        # 1. Whitespace säubern
        lines = [line.strip() for line in sql.strip().splitlines() if line.strip()]
        # 2. Einheitliche Einrückung
        indent = " " * 7  # nach "SQL: "
        formatted_sql = ("\n" + indent).join(lines)
        # 3. Params anhängen
        if params:
            indent = " " * 3
            return f"SQL: {formatted_sql}\n{indent}PARAMS: {params}"
        return f"SQL: {formatted_sql}"

    # ------------------------
    # DataFrame helpers
    # ------------------------

    def write_dataframe(
            self, df: pd.DataFrame, table_name: str, if_exists: Literal["fail", "replace", "append"] = "append"
    ) -> int:
        full_table = self._prefixed(table_name)
        with self.engine.begin() as conn:
            df.to_sql(full_table, conn, if_exists=if_exists, index=False)
        return len(df)

    def insert_dataframe(
            self, df: pd.DataFrame, table_name: str, if_exists: str = "append"
    ) -> int:
        inspector = inspect(self.engine)
        full_table = self._prefixed(table_name)

        db_columns = {c["name"] for c in inspector.get_columns(full_table)}
        filtered_df = df[[c for c in df.columns if c in db_columns]]

        with self.engine.begin() as conn:
            filtered_df.to_sql(full_table, conn, if_exists=if_exists, index=False)

        return len(filtered_df)

    # ------------------------
    # Read helpers
    # ------------------------

    def fetch_one(self, sql: str, params: dict = None) -> Optional[Dict]:
        self._log_sql(sql, params)
        query = text(sql)
        with self.engine.begin() as conn:
            row = conn.execute(query, params or {}).mappings().first()
            return dict(row) if row else None

    def fetch_all(self, sql: str, params: dict = None) -> List[Dict]:
        self._log_sql(sql, params)
        query = text(sql)
        with self.engine.begin() as conn:
            return [dict(r) for r in conn.execute(query, params or {}).mappings()]

    def read_query(self, sql: str, params: dict = None) -> pd.DataFrame:
        self._log_sql(sql, params)
        query = text(sql)
        with self.engine.begin() as conn:
            return pd.read_sql(query, conn, params=params or {})

    # ------------------------
    # Transaktions-Unterstützung
    # ------------------------

    @contextmanager
    def transaction(self):
        """
        Context Manager für atomare Operationen.
        Alle execute_write / insert_and_get_id Aufrufe innerhalb des Blocks
        teilen sich dieselbe Connection und werden gemeinsam committed oder
        bei Exception zurückgerollt.
        """
        with self.engine.begin() as conn:
            self._conn = conn
            try:
                yield conn
            finally:
                self._conn = None

    # ------------------------
    # Write helpers
    # ------------------------

    def execute_write(self, sql: str, params: dict = None, force: bool = False) -> int:
        self._log_sql(sql, params, force)
        query = text(sql)
        if self._conn is not None:
            result = self._conn.execute(query, params or {})
            return result.rowcount
        with self.engine.begin() as conn:
            result = conn.execute(query, params or {})
            return result.rowcount

    def execute_many(self, sql: str, param_list: List[dict]) -> None:
        query = text(sql)
        if self._conn is not None:
            self._conn.execute(query, param_list)
            return
        with self.engine.begin() as conn:
            conn.execute(query, param_list)

    def insert_and_get_id(self, sql: str, params: dict) -> int:
        query = text(sql)
        if self._conn is not None:
            result = self._conn.execute(query, params)
            return result.lastrowid
        with self.engine.begin() as conn:
            result = conn.execute(query, params)
            return result.lastrowid

    # ------------------------
    # Domain-independent helpers
    # ------------------------

    def get_all_raw_trades(self, env_up: str, table: str) -> pd.DataFrame:
        full_table = self._prefixed(table)
        sql = f"""
            SELECT *
            FROM {full_table}
            WHERE processed = 0
              AND environment = :env
            ORDER BY dateTime ASC, symbol ASC
        """
        return self.read_query(sql, {"env": env_up})

    def _get_existing_checksums(self, table: str, checksums) -> set:
        if not checksums:
            return set()

        full_table = self._prefixed(table)
        sql = f"""
            SELECT checksum
            FROM {full_table}
            WHERE checksum IN :checksums
        """

        with self.engine.begin() as conn:
            return set(
                conn.execute(
                    text(sql), {"checksums": tuple(checksums)}
                ).scalars().all()
            )

    def get_existing_trades_checksums(self, checksums) -> set:
        return self._get_existing_checksums(TABLE_TRADES_RAW, checksums)

    def get_existing_fx_checksums(self, checksums) -> set:
        return self._get_existing_checksums(TABLE_TRADES_FX, checksums)


# ============================================================
# Trade Repository (Domain Layer)
# ============================================================

class TradeRepository:
    def __init__(self, db: DBAccess):
        self.db = db

    def _prefixed(self, table_name: str) -> str:
        return self.db._prefixed(table_name)

    # ------------------------
    # Symbols
    # ------------------------

    def get_symbol(self, symbol: str, asset_category: str) -> Optional[Dict]:
        full_table = self._prefixed(TABLE_SYMBOLS)
        sql = f"""
            SELECT id
            FROM {full_table}
            WHERE symbol = :symbol
              AND assetCategory = :assetCategory
        """
        return self.db.fetch_one(
            sql, {"symbol": symbol, "assetCategory": asset_category}
        )

    def insert_symbol(self, symbol: str, asset_category: str, isin: str,
                      underlyingSymbol: str, conid: int, underlyingConid: int,
                      environment: str) -> int:
        full_table = self._prefixed(TABLE_SYMBOLS)
        sql = f"""
            INSERT INTO {full_table} 
                (symbol, assetCategory, isin, underlyingSymbol, conid, underlyingConid, environment)
            VALUES 
                (:symbol, :assetCategory, :isin, :underlyingSymbol, :conid, :underlyingConid, :environment)
            ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)
        """
        return self.db.insert_and_get_id(
            sql, {"symbol": symbol, "assetCategory": asset_category, "isin": isin,
                  "underlyingSymbol": underlyingSymbol, "conid": conid, "underlyingConid": underlyingConid,
                  "environment": environment, },
        )

    def get_symbols_bulk(self, symbols, asset_categories) -> List[Dict]:
        if not symbols:
            return []

        values = [
            {"symbol": s, "assetCategory": c}
            for s, c in zip(symbols, asset_categories)
        ]

        full_table = self._prefixed(TABLE_SYMBOLS)
        sql = f"""
            SELECT symbol, assetCategory, id
            FROM {full_table}
            WHERE (symbol, assetCategory) IN (
                SELECT :symbol, :assetCategory
            )
        """

        with self.db.engine.begin() as conn:
            return conn.execute(text(sql), values).mappings().all()

    # ------------------------
    # Trades
    # ------------------------

    def insert_record(
            self, schema_class: Type[BaseSchema], record: Dict[str, Any]
    ) -> int:
        schema_class.validate_and_raise(record)

        fields = schema_class.get_db_field_names()
        placeholders = schema_class.get_db_placeholders()
        full_table = self._prefixed(schema_class.TABLE_NAME)

        sql = f"""
            INSERT INTO {full_table} ({', '.join(fields)})
            VALUES ({placeholders})
        """

        params = {field: record.get(field) for field in schema_class.FIELDS}
        return self.db.insert_and_get_id(sql, params)

    def insert_open_trade(self, trade: Dict[str, Any]) -> int:
        return self.insert_record(OpenTradeSchema, trade)

    def insert_closed_trade(self, trade: Dict[str, Any]) -> int:
        return self.insert_record(ClosedTradeSchema, trade)

    def get_open_trade(self, asset_category: str, symbol: str) -> Optional[Dict]:
        full_table = self._prefixed(TABLE_TRADES_OPEN)
        sql = f"""
            SELECT *
            FROM {full_table}
            WHERE assetCategory = :assetCategory
              AND symbol = :symbol
              AND processed = 0
        """
        return self.db.fetch_one(
            sql, {"assetCategory": asset_category, "symbol": symbol}
        )

    def get_open_trades(self, asset_category: str, symbol: str) -> List[Dict]:
        full_table = self._prefixed(TABLE_TRADES_OPEN)
        sql = f"""
            SELECT *
            FROM {full_table}
            WHERE assetCategory = :assetCategory
              AND symbol = :symbol
              AND processed = 0
              ORDER BY dateTime ASC;
        """
        return self.db.fetch_all(
            sql, {"assetCategory": asset_category, "symbol": symbol}
        )

    def get_active_campaign_id_by_symbol(self, symbol: str) -> Optional[int]:
        """Sucht die aktive oder ausstehende Kampagne für ein Symbol in der DB."""
        full_table = self._prefixed(TABLE_TRADING_CAMPAIGNS)
        sql = f"""
            SELECT id FROM {full_table}
            WHERE symbol = :symbol
              AND status IN ('ACTIVE', 'PENDING')
            ORDER BY id DESC
            LIMIT 1
        """
        row = self.db.fetch_one(sql, {"symbol": symbol})
        return int(row["id"]) if row else None

    def mark_open_trade_processed(self, trade_id):
        return self.mark_trade_processed(TABLE_TRADES_OPEN, trade_id)

    # Open-Trades werden nicht mehr gelöscht, es wird nur processed = 1 gesetzt. Damit bleibt die History (id) erhalten.
    def delete_open_trade(self, trade_id: int) -> int:
        return self.mark_trade_processed(TABLE_TRADES_OPEN, trade_id)
        # full_table = self._prefixed(TABLE_TRADES_OPEN)
        # sql = f"DELETE FROM {full_table} WHERE id = :id"
        # return self.db.execute_write(sql, {"id": int(trade_id)})

    def update_open_trade(self, updates: Dict[str, Any]) -> int:
        trade_id = int(updates["id"])
        updates = {k: v for k, v in updates.items() if k != "id"}

        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        full_table = self._prefixed(TABLE_TRADES_OPEN)

        sql = f"""
            UPDATE {full_table}
            SET {set_clause}
            WHERE id = :id
        """

        updates["id"] = trade_id
        return self.db.execute_write(sql, updates)

    def mark_trade_processed(self, table: str, trade_id: int) -> int:
        full_table = self._prefixed(table)
        sql = f"UPDATE {full_table} SET processed = 1 WHERE id = :id"
        return self.db.execute_write(sql, {"id": int(trade_id)})

    def update_notes_tag_pivot(self, trade_id: int) -> None:
        for table in (TABLE_TRADE_NOTES, TABLE_TRADE_TAG_PIVOT):
            full_table = self._prefixed(table)
            sql = f"""
                UPDATE {full_table}
                SET trade_type = 'closed'
                WHERE trade_id = :id
            """
            self.db.execute_write(sql, {"id": int(trade_id)})
