# tools/demo/seed_log_and_psychology.py
#
# Füllt die Demo-DB (ibkr_demo, TEST/demo_) mit plausiblen Trade-Log- und
# Psychology-Einträgen, verknüpft mit den bereits importierten echten
# Demo-Kampagnen/-Trades (siehe tools/demo/README.md). Ohne dieses Skript sind
# "Log" und "Psychologie" in der Demo komplett leer, obwohl beide Module
# freigeschaltet sind — wirkt für Demo-Besucher unfertig.
#
# Nicht idempotent mit Merge-Logik — löscht vor dem Einfügen alle bestehenden
# Zeilen mit environment='TEST' in trade_planner/trade_planner_legs/
# psychology_entries/psychology_compliance_results, damit das Skript beliebig
# oft neu laufen kann (z.B. nach einem frischen reset_IBKR_DB.py-Lauf).
#
# Verwendung (wie andere Demo-Tools: DB_NAME_TEST auf die isolierte Demo-DB
# umbiegen, NICHT in .env schreiben):
#   $env:DB_NAME_TEST = "ibkr_demo"
#   .venv\Scripts\python -m tools.demo.seed_log_and_psychology

import random
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import create_engine, text

from src.config import get_db_url

ENV = "TEST"
PREFIX = "demo_"
RNG = random.Random(42)  # fester Seed — reproduzierbares Ergebnis bei Re-Runs


def t(name: str) -> str:
    return f"{PREFIX}{name}"


# ── Log (trade_planner) ──────────────────────────────────────────────────────

# campaign.strategy ist eine grobe Kategorie (kein Freitext-Options-Strategiename) —
# LogForm.prefillFromCampaign() übernimmt sie 1:1 in trade_planner.strategy, hier
# identisch nachgebildet.
EXIT_PLANS = {
    "DIRECT_INVEST": [
        "Langfristig halten, Stop bei -15% bzw. wenn sich die fundamentale These ändert",
        "Kernposition — kein fester Exit, jährliche Überprüfung der These",
        "Verkauf bei +30% oder wenn ein besseres Setup das Kapital braucht",
        "Stop-Loss bei -10%, sonst laufen lassen",
    ],
    "BONUS/CASHFLOW": [
        "TP bei 50% der Prämie, bei Zuteilung Covered Call auf die Aktien schreiben",
        "Bis Verfall halten wenn weit OTM, sonst bei 21 DTE rollen",
        "TP bei 50-60%, DTE-Stop bei 21 Tagen",
        "Prämie mitnehmen bei 50%, keine Anpassung ohne klaren Vorteil",
    ],
    "HEDGE/SPECULATION": [
        "Absicherung auflösen sobald das Makro-Risiko vorbei ist",
        "Spekulative Position — hartes Stop bei -50% des Einsatzes",
        "Teilgewinn bei +100%, Rest laufen lassen mit nachgezogenem Stop",
        "Zeitlich begrenzt bis Event vorbei, danach Position schließen unabhängig vom Kurs",
    ],
}

RATIONALES = {
    "DIRECT_INVEST": [
        "{symbol} nach Kursrücksetzer auf attraktivem Bewertungsniveau, Sektor-Fundamentaldaten intakt",
        "Kleine Position zum Aufbau eines Kern-Investments in {symbol}",
        "{symbol} zeigt relative Stärke im Sektor, technisches Setup an Unterstützung",
        "Nachkauf {symbol} nach Update der Quartalszahlen",
    ],
    "BONUS/CASHFLOW": [
        "Prämie auf {symbol} attraktiv bei aktueller IV, Strike deutlich OTM gewählt",
        "Cashflow-Trade auf {symbol} im Rahmen der Wheel-Strategie",
        "{symbol} bietet gute Prämie bei überschaubarem Zuteilungsrisiko",
        "Regelmäßiger Einkommens-Trade auf {symbol}, Strike nach System gewählt",
    ],
    "HEDGE/SPECULATION": [
        "Absicherung des Portfolios über {symbol} gegen kurzfristiges Abwärtsrisiko",
        "Spekulativer Trade auf {symbol} rund um erwartete Volatilität",
        "{symbol}-Position zur Portfolio-Absicherung vor bekanntem Makro-Event",
        "Directional Bet auf {symbol}, klein dimensioniert wegen hohem Risiko",
    ],
}

LEG_TYPE_MAP = {
    ("P", "SELL"): "SP",
    ("C", "SELL"): "SC",
    ("P", "BUY"): "LP",
    ("C", "BUY"): "LC",
}
# Alle CLOSED-Kampagnen werden geloggt; von den ACTIVE-Kampagnen bewusst nur ein
# Teil, damit die "nicht dokumentiert"-Sektion in der Demo weiterhin etwas zeigt
# (realistisches Verhalten — niemand loggt 100% seiner Trades).
UNLOGGED_ACTIVE_CAMPAIGN_IDS = {15, 19, 22, 32, 38, 43, 47}


def seed_log(conn) -> int:
    campaigns = conn.execute(text(f"""
        SELECT id, symbol, strategy, status, start_date, end_date
        FROM `{t('trading_campaigns')}`
        WHERE environment = :env
        ORDER BY start_date
    """), {"env": ENV}).mappings().all()

    pnl_by_campaign = dict(conn.execute(text(f"""
        SELECT campaign_id, SUM(realized_pnl) AS pnl
        FROM `{t('campaign_ledger')}`
        WHERE environment = :env
        GROUP BY campaign_id
    """), {"env": ENV}).all())

    inserted = 0

    for c in campaigns:
        if c["status"] == "ACTIVE" and c["id"] in UNLOGGED_ACTIVE_CAMPAIGN_IDS:
            continue
        if c["status"] == "PENDING":
            continue  # zu kurzlebig/unklar für einen sinnvollen Log-Eintrag

        category = c["strategy"] or "DIRECT_INVEST"
        is_closed = c["status"] == "CLOSED"

        header = {
            "environment": ENV,
            "campaign_id": c["id"],
            "underlying": c["symbol"],
            "date_open": c["start_date"].date() if hasattr(c["start_date"], "date") else c["start_date"],
            "strategy": category,
            "exit_plan": RNG.choice(EXIT_PLANS.get(category, EXIT_PLANS["DIRECT_INVEST"])),
            "rationale": RNG.choice(RATIONALES.get(category, RATIONALES["DIRECT_INVEST"])).format(symbol=c["symbol"]),
            "status": "closed" if is_closed else "open",
            "date_close": None,
            "realized_pnl": None,
            "actual_dte": None,
        }

        if is_closed and c["end_date"]:
            end = c["end_date"].date() if hasattr(c["end_date"], "date") else c["end_date"]
            header["date_close"] = end
            header["actual_dte"] = (end - header["date_open"]).days
            pnl = pnl_by_campaign.get(c["id"])
            header["realized_pnl"] = round(float(pnl), 2) if pnl else None

        result = conn.execute(text(f"""
            INSERT INTO `{t('trade_planner')}`
                (environment, campaign_id, underlying, date_open, strategy, exit_plan,
                 rationale, status, date_close, realized_pnl, actual_dte, created_at, updated_at)
            VALUES
                (:environment, :campaign_id, :underlying, :date_open, :strategy, :exit_plan,
                 :rationale, :status, :date_close, :realized_pnl, :actual_dte, NOW(), NOW())
        """), header)
        plan_id = result.lastrowid
        inserted += 1

        opening_legs = conn.execute(text(f"""
            SELECT putCall, buySell, strike, tradePrice, commission, expiry, dateTime
            FROM `{t('campaign_ledger')}`
            WHERE campaign_id = :cid AND environment = :env
              AND assetCategory = 'OPT'
              AND action IN ('OPT_PUT_SELL','OPT_CALL_SELL','OPT_PUT_BUY','OPT_CALL_BUY')
            ORDER BY dateTime
            LIMIT 4
        """), {"cid": c["id"], "env": ENV}).mappings().all()

        for sort_order, leg in enumerate(opening_legs):
            leg_type = LEG_TYPE_MAP.get((leg["putCall"], leg["buySell"]))
            if not leg_type:
                continue
            dte = None
            if leg["expiry"] and leg["dateTime"]:
                expiry_d = leg["expiry"] if not hasattr(leg["expiry"], "date") else leg["expiry"]
                open_d = leg["dateTime"].date() if hasattr(leg["dateTime"], "date") else leg["dateTime"]
                dte = (expiry_d - open_d).days

            conn.execute(text(f"""
                INSERT INTO `{t('trade_planner_legs')}`
                    (plan_id, leg_type, dte, strike, premium, fees, sort_order)
                VALUES
                    (:plan_id, :leg_type, :dte, :strike, :premium, :fees, :sort_order)
            """), {
                "plan_id": plan_id,
                "leg_type": leg_type,
                "dte": dte,
                "strike": leg["strike"],
                "premium": leg["tradePrice"],
                "fees": abs(float(leg["commission"])) if leg["commission"] is not None else None,
                "sort_order": sort_order,
            })

    return inserted


# ── Psychology (psychology_entries + compliance_results) ───────────────────

# ruleset_id-Zuordnung wird zur Laufzeit per Name aus der DB gelesen (siehe
# seed_psychology_rulesets.py — Namen sind dort die einzige stabile Referenz).
RULESET_NAME_STK   = "Aktien Exit (Verkauf)"
RULESET_NAME_PUT   = "Short Put / CSP"
RULESET_NAME_CALL  = "Short Call / Covered Call"
RULESET_NAME_IC    = "Iron Condor"

# (trade_id, ruleset_name) — handverlesene Auswahl echter geschlossener Demo-Trades,
# quer über den Zeitraum und mit bewusster Gewinn/Verlust-Mischung fuer eine
# glaubwuerdige Psychology-Historie.
STK_TRADE_IDS = [1, 3, 8, 15, 20, 22, 25, 39, 59, 61, 62, 67, 77, 85, 108, 120]
OPT_PUT_CALL_TRADE_IDS = [7, 14, 21, 26, 31, 48, 66, 76, 109, 131]
IC_TRADE_ID = 119

MOTIVATIONS = ["SYSTEM", "SYSTEM", "SYSTEM", "FOMO", "REVENGE", "BOREDOM", "IMPULSE"]
MARKET_CONTEXTS = ["trending", "choppy", "high_iv", "low_iv", "news"]

LESSONS = {
    "SYSTEM": [
        "Plan eingehalten, keine Überraschungen — genau so soll es laufen.",
        "Sauber nach System gehandelt, Ergebnis war zweitrangig.",
        "Diszipliniert exekutiert, kein Grund etwas zu ändern.",
    ],
    "FOMO": [
        "Zu spät eingestiegen, dem Move hinterhergelaufen — nächstes Mal auf den eigenen Trigger warten.",
        "FOMO beim Entry gespürt, Positionsgröße im Nachhinein zu groß gewählt.",
        "Kurs schon stark gelaufen, trotzdem rein — Lehre: Geduld für den nächsten Pullback.",
    ],
    "REVENGE": [
        "Nach dem letzten Verlust zu schnell wieder rein — Cool-down-Regel nächstes Mal einhalten.",
        "Position vergrößert um den Vortag auszugleichen, kein guter Reflex.",
        "Revenge-Trading erkannt, aber zu spät — Pause nach Verlusttagen fest einplanen.",
    ],
    "BOREDOM": [
        "Trade aus Langeweile, kein echtes Setup vorhanden gewesen.",
        "Ohne klaren Trigger eingestiegen, nur weil schon lange nichts passiert ist.",
        "Setup war schwach, trotzdem gehandelt — nächstes Mal lieber am Seitenrand bleiben.",
    ],
    "IMPULSE": [
        "Spontan reagiert ohne Plan zu prüfen — Checkliste vor Entry künftig konsequenter nutzen.",
        "Impulsiv gehandelt, Regelwerk im Kopf übersprungen.",
        "Kein Fehler im Ergebnis, aber der Prozess war impulsiv — Prozess zählt mehr als Ergebnis.",
    ],
}


def compliance_for(motivation: str, rng: random.Random) -> tuple[bool, bool]:
    """Gibt (complied, tempted) für eine Regel zurück, Verteilung abhängig von der Motivation."""
    if motivation == "SYSTEM":
        return rng.random() < 0.9, rng.random() < 0.05
    if motivation in ("FOMO", "IMPULSE"):
        return rng.random() < 0.45, rng.random() < 0.55
    if motivation == "REVENGE":
        return rng.random() < 0.3, rng.random() < 0.6
    return rng.random() < 0.6, rng.random() < 0.3  # BOREDOM


def get_ruleset(conn, name: str) -> tuple[int, list[int]]:
    ruleset_id = conn.execute(text(f"""
        SELECT id FROM `{t('psychology_rulesets')}` WHERE name = :name AND environment = :env LIMIT 1
    """), {"name": name, "env": ENV}).scalar()
    rule_ids = [r[0] for r in conn.execute(text(f"""
        SELECT id FROM `{t('psychology_rules')}` WHERE ruleset_id = :rid ORDER BY sort_order
    """), {"rid": ruleset_id}).all()]
    return ruleset_id, rule_ids


def seed_psychology(conn) -> int:
    rulesets = {
        "STK": get_ruleset(conn, RULESET_NAME_STK),
        "PUT": get_ruleset(conn, RULESET_NAME_PUT),
        "CALL": get_ruleset(conn, RULESET_NAME_CALL),
        "IC": get_ruleset(conn, RULESET_NAME_IC),
    }

    plan = [(tid, "STK") for tid in STK_TRADE_IDS] \
        + [(tid, None) for tid in OPT_PUT_CALL_TRADE_IDS] \
        + [(IC_TRADE_ID, "IC")]

    trade_ids = [tid for tid, _ in plan]
    trades = {
        row["id"]: row
        for row in conn.execute(text(f"""
            SELECT id, symbol, underlyingSymbol, assetCategory, putCall, dateTimeClose, profit
            FROM `{t('trades_close')}`
            WHERE id IN :ids AND environment = :env
        """).bindparams(ids=tuple(trade_ids)), {"env": ENV}).mappings().all()
    }

    inserted = 0

    for trade_id, kind in plan:
        trade = trades.get(trade_id)
        if not trade:
            continue

        if kind == "STK":
            bucket = "STK"
        elif kind == "IC":
            bucket = "IC"
        else:
            bucket = "PUT" if trade["putCall"] == "P" else "CALL"

        ruleset_id, rule_ids = rulesets[bucket]
        pnl = float(trade["profit"])
        is_win = pnl >= 0

        motivation = RNG.choice(MOTIVATIONS) if not is_win else RNG.choices(
            MOTIVATIONS, weights=[3, 3, 3, 1, 1, 1, 1]
        )[0]
        emotion_pre = RNG.randint(3, 5) if motivation == "SYSTEM" else RNG.randint(1, 4)
        emotion_post = RNG.randint(4, 5) if is_win else RNG.randint(1, 3)

        symbol = trade["underlyingSymbol"] or trade["symbol"]
        lesson = RNG.choice(LESSONS[motivation])

        entry_data = {
            "trade_id": str(trade_id),
            "opt_strategyID": None,
            "trade_type": "closed",
            "ruleset_id": ruleset_id,
            "symbol": symbol,
            "trade_date": trade["dateTimeClose"].date() if hasattr(trade["dateTimeClose"], "date") else trade["dateTimeClose"],
            "pnl": round(pnl, 2),
            "emotion_pre": emotion_pre,
            "emotion_post": emotion_post,
            "motivation": motivation,
            "market_context": RNG.choice(MARKET_CONTEXTS),
            "lesson": lesson,
            "environment": ENV,
        }

        result = conn.execute(text(f"""
            INSERT INTO `{t('psychology_entries')}`
                (trade_id, opt_strategyID, trade_type, ruleset_id, symbol, trade_date, pnl,
                 emotion_pre, emotion_post, motivation, market_context, lesson, environment,
                 created_at, updated_at)
            VALUES
                (:trade_id, :opt_strategyID, :trade_type, :ruleset_id, :symbol, :trade_date, :pnl,
                 :emotion_pre, :emotion_post, :motivation, :market_context, :lesson, :environment,
                 NOW(), NOW())
        """), entry_data)
        entry_id = result.lastrowid
        inserted += 1

        for rule_id in rule_ids:
            complied, tempted = compliance_for(motivation, RNG)
            conn.execute(text(f"""
                INSERT INTO `{t('psychology_compliance_results')}` (entry_id, rule_id, complied, tempted)
                VALUES (:entry_id, :rule_id, :complied, :tempted)
            """), {"entry_id": entry_id, "rule_id": rule_id, "complied": complied, "tempted": tempted})

    return inserted


def clear_existing(conn) -> None:
    conn.execute(text(f"""
        DELETE FROM `{t('psychology_compliance_results')}`
        WHERE entry_id IN (SELECT id FROM `{t('psychology_entries')}` WHERE environment = :env)
    """), {"env": ENV})
    conn.execute(text(f"DELETE FROM `{t('psychology_entries')}` WHERE environment = :env"), {"env": ENV})
    conn.execute(text(f"""
        DELETE FROM `{t('trade_planner_legs')}`
        WHERE plan_id IN (SELECT id FROM `{t('trade_planner')}` WHERE environment = :env)
    """), {"env": ENV})
    conn.execute(text(f"DELETE FROM `{t('trade_planner')}` WHERE environment = :env"), {"env": ENV})


def main() -> None:
    db_url = get_db_url("test")
    engine = create_engine(db_url)

    print("=" * 65)
    print("  SEED LOG + PSYCHOLOGY (Demo)")
    print("=" * 65)

    with engine.begin() as conn:
        clear_existing(conn)
        log_count = seed_log(conn)
        psych_count = seed_psychology(conn)

    print(f"  Log-Einträge angelegt:        {log_count}")
    print(f"  Psychology-Einträge angelegt: {psych_count}")
    print("=" * 65)


if __name__ == "__main__":
    main()
