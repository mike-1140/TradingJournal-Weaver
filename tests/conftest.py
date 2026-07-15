import pandas as pd
import pytest


# --- Fake Logger --------------------------------------------------------------
class DummyLogger:
    """In-Memory-Logger — speichert Log-Aufrufe zur Pruefung in Tests."""
    def __init__(self):
        self.records = []

    def debug(self, msg): self.records.append(("DEBUG", msg))
    def info(self, msg): self.records.append(("INFO", msg))
    def warning(self, msg): self.records.append(("WARNING", msg))
    def error(self, msg): self.records.append(("ERROR", msg))
    def critical(self, msg): self.records.append(("CRITICAL", msg))

    def last(self, level=None):
        """Letzte Log-Meldung, optional nach Level gefiltert."""
        if level:
            for lvl, msg in reversed(self.records):
                if lvl == level:
                    return msg
        return self.records[-1][1] if self.records else None


@pytest.fixture
def dummy_logger():
    """Frischer In-Memory-Logger je Test."""
    return DummyLogger()


# --- Fake DBAccess ------------------------------------------------------------
class DummyDBAccess:
    """
    Mock der DB-Schicht — speichert Insert-Aufrufe im Speicher.
    Gleiche Schnittstelle wie DBAccess, aber ohne I/O.
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
        return pd.DataFrame()

    def commit(self): return True
    def close(self): self.connected = False
    def __repr__(self): return f"<DummyDBAccess inserts={len(self.inserts)}>"


@pytest.fixture
def dummy_db():
    """In-Memory-Fake fuer DBAccess."""
    return DummyDBAccess()
