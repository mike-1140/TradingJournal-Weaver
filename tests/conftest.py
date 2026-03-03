import pytest
import pandas as pd
import logging
from types import SimpleNamespace

# 🧱 1. Fake Logger ------------------------------------------------------------
class DummyLogger:
    """A simple in-memory logger that stores logs for test inspection."""
    def __init__(self):
        self.records = []

    def debug(self, msg): self.records.append(("DEBUG", msg))
    def info(self, msg): self.records.append(("INFO", msg))
    def warning(self, msg): self.records.append(("WARNING", msg))
    def error(self, msg): self.records.append(("ERROR", msg))
    def critical(self, msg): self.records.append(("CRITICAL", msg))

    def last(self, level=None):
        """Return last logged message optionally filtered by level."""
        if level:
            for lvl, msg in reversed(self.records):
                if lvl == level:
                    return msg
        return self.records[-1][1] if self.records else None

@pytest.fixture
def dummy_logger():
    """Provides a fresh in-memory logger for each test."""
    return DummyLogger()


# 🧱 2. Fake DBAccess ----------------------------------------------------------
class DummyDBAccess:
    """
    Mock DB layer that stores insert calls in memory.
    Provides same interface as real DBAccess, but without I/O.
    """
    def __init__(self):
        self.inserts = []
        self.selects = []
        self.connected = True

    def insert_dataframe(self, df, table_name, if_exists="append"):
        self.inserts.append((table_name, len(df)))
        return True

    def select(self, query, params=None):
        self.selects.append((query, params))
        # Return empty DataFrame by default
        return pd.DataFrame()

    def commit(self): return True
    def close(self): self.connected = False
    def __repr__(self): return f"<DummyDBAccess inserts={len(self.inserts)}>"

@pytest.fixture
def dummy_db():
    """Provides an in-memory fake DBAccess object."""
    return DummyDBAccess()


# 🧱 3. Utility Fixtures -------------------------------------------------------
@pytest.fixture
def sample_trade_df():
    """A sample minimal trades DataFrame for testing inserts/checksums."""
    return pd.DataFrame([{
        "symbol": "AAPL",
        "tradeID": "T123",
        "tradeDate": "2023-11-17",
        "quantity": 1,
        "tradePrice": 180.00,
        "netCash": 125.00,
        "buySell": "SELL"
    }])


@pytest.fixture
def fake_env(monkeypatch, tmp_path):
    """Fake environment with temp directory for file ops."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FLEX_IMPORT_TEST", "1")
    return tmp_path


# 🧱 4. Autoapply Logger to flex_import (optional) -----------------------------
@pytest.fixture(autouse=True)
def patch_logger(monkeypatch, dummy_logger):
    """Automatically patch logging.getLogger to use DummyLogger."""
    monkeypatch.setattr(logging, "getLogger", lambda name=None: dummy_logger)
    yield
