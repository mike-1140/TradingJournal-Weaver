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


# --- Fake TradeRepository -------------------------------------------------------
class FakeTradeRepository:
    """
    In-Memory-Ersatz fuer TradeRepository -- bildet nur die Methoden nach, die
    process_raw_trade() tatsaechlich aufruft (get_open_trades, insert_open_trade,
    insert_closed_trade, mark_trade_processed). Keine echte DB-Verbindung.
    """
    def __init__(self):
        self._open_trades = []   # Liste von Dicts, wie Zeilen aus trades_open
        self.closed_trades = []  # aufgezeichnete insert_closed_trade()-Aufrufe
        self.processed = []      # aufgezeichnete mark_trade_processed()-Aufrufe (table, id)
        self._next_id = 1

    def seed_open_trade(self, **fields):
        """Legt eine offene Tranche an, wie sie aus der DB kaeme (inkl. 'id')."""
        trade = {"id": self._next_id, "processed": 0}
        trade.update(fields)
        self._open_trades.append(trade)
        self._next_id += 1
        return trade

    def get_open_trades(self, asset_category, symbol, conid=None):
        return [
            t for t in self._open_trades
            if t["assetCategory"] == asset_category and t["symbol"] == symbol and t["processed"] == 0
        ]

    def insert_open_trade(self, trade):
        new_trade = dict(trade)
        new_trade["id"] = self._next_id
        new_trade.setdefault("processed", 0)
        self._open_trades.append(new_trade)
        self._next_id += 1
        return new_trade["id"]

    def insert_closed_trade(self, trade):
        self.closed_trades.append(dict(trade))
        self._next_id += 1
        return self._next_id

    def mark_trade_processed(self, table, trade_id):
        self.processed.append((table, int(trade_id)))
        for t in self._open_trades:
            if t["id"] == int(trade_id):
                t["processed"] = 1
        return 1


@pytest.fixture
def fake_repo():
    """Frisches In-Memory-Repository je Test."""
    return FakeTradeRepository()


# --- Fake InventoryTracker -------------------------------------------------------
class FakeInventoryTracker:
    """
    In-Memory-Ersatz fuer InventoryTracker -- die echte Klasse schreibt bei
    link_to_campaign_new() direkt per SQL ins campaign_ledger. Hier wird der
    Aufruf nur aufgezeichnet, damit ein Test die gebuchte Action/den P&L pruefen kann.
    """
    def __init__(self, holdings=None):
        self.holdings = holdings if holdings is not None else {}
        self.ledger_calls = []

    def link_to_campaign_new(self, **kwargs):
        self.ledger_calls.append(kwargs)


@pytest.fixture
def fake_tracker():
    """Frischer In-Memory-Tracker je Test."""
    return FakeInventoryTracker()
