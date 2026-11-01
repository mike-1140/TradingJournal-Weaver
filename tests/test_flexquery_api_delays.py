# Regressionstest: Beim zweiten Lauf am selben Tag wartete main() vor jeder Query (beim Token-Wechsel
# 30 Sekunden), obwohl gar keine Anfrage an IBKR ging. Gewartet wird nur noch vor echten Anfragen.
# Laeuft ohne Netzwerk: Abruf, Merker und Pause sind ersetzt.

import pytest

from src import get_flexquery_api as api


class _Logger:
    def info(self, *args):
        pass

    def error(self, *args):
        pass


@pytest.fixture
def run(monkeypatch):
    def _run(queries, fetched):
        sleeps, requests = [], []
        monkeypatch.setattr(api, "_parse_queries", lambda: queries)
        monkeypatch.setattr(api, "_ensure_dirs", lambda: None)
        monkeypatch.setattr(api, "setup_logging", lambda *a, **k: (_Logger(), None))
        monkeypatch.setattr(api, "_already_fetched_today", lambda qid: "datei.xml" if qid in fetched else None)
        monkeypatch.setattr(api.time, "sleep", sleeps.append)

        def fake_fetch(token, qid, logger):
            if qid in fetched:
                return False
            requests.append(qid)
            return True

        monkeypatch.setattr(api, "_fetch_query", fake_fetch)
        return api.main(), sleeps, requests

    return _run


def test_alles_schon_geholt_keine_pause(run):
    cnt, sleeps, requests = run([("A", "1"), ("A", "2"), ("B", "3")], fetched={"1", "2", "3"})

    assert (cnt, sleeps, requests) == (0, [], [])


def test_pause_zwischen_echten_anfragen(run):
    cnt, sleeps, requests = run([("A", "1"), ("A", "2"), ("B", "3")], fetched=set())

    assert cnt == 3
    assert requests == ["1", "2", "3"]
    assert sleeps == [api.QUERY_DELAY, api.TOKEN_DELAY]


def test_uebersprungene_query_zaehlt_nicht_als_token_wechsel(run):
    # B wird uebersprungen: zwischen den echten Anfragen mit A bleibt es die kurze Pause
    _, sleeps, requests = run([("A", "1"), ("B", "2"), ("A", "3")], fetched={"2"})

    assert requests == ["1", "3"]
    assert sleeps == [api.QUERY_DELAY]


def test_pause_richtet_sich_nach_der_letzten_echten_anfrage(run):
    # A wird uebersprungen, die erste echte Anfrage braucht keine Pause, der Wechsel zu C schon
    _, sleeps, requests = run([("A", "1"), ("B", "2"), ("C", "3")], fetched={"1"})

    assert requests == ["2", "3"]
    assert sleeps == [api.TOKEN_DELAY]
