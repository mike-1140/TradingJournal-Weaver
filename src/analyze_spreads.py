"""
Analyse von 0DTE Spreads in der campaign_ledger-Tabelle.
Zeigt pro Kampagne und Tag: Aktionsfluss, Cashflow, Netto-P&L.

Aufruf:
  python src/analyze_spreads.py autom_paper
  python src/analyze_spreads.py autom_paper --user mike_
  python src/analyze_spreads.py autom_paper --campaign 42
"""

import argparse

import pandas as pd
from sqlalchemy import text

from src.config import get_engine, TABLE_PREFIX, TABLE_CAMPAIGN_LEDGER, TABLE_TRADING_CAMPAIGNS

DE_DAYS = {0: 'Montag', 1: 'Dienstag', 2: 'Mittwoch', 3: 'Donnerstag',
           4: 'Freitag', 5: 'Samstag', 6: 'Sonntag'}

ACTION_LABELS = {
    'TRADE_OPEN':           'OPEN   ',
    'TRADE_CLOSE_FULL':     'CLOSE  ',
    'TRADE_CLOSE_PARTIAL':  'PARTIAL',
    'OPTION_EXPIRATION':    'EXPIRY ',
    'OPTION_EXERCISE':      'EXERCS ',
    'CASH_SETTLEMENT':      'SETTLMT',
    'FX_EXCHANGE_FROM':     'FX_FROM',
    'FX_EXCHANGE_TO':       'FX_TO  ',
    'SPLIT_REST':           'SPLIT  ',
}

WIDTH = 64           # Innenbreite der Box (Zeichen zwischen │ und │)
# Trade-Zeile:   1+5+2+7+2+4+2+24+2+13+2 = 64
# Summary-Zeile: 2+46+1+13+2            = 64  → Label-Breite = WIDTH-18 = 46
_SUMMARY_LABEL_W = WIDTH - 18   # = 46  (2+L+1+13+2 = 64)


def fmt_cash(val) -> str:
    """Formatiert Cashflow-Wert mit Vorzeichen und $ Zeichen. Immer 13 Zeichen."""
    try:
        f = float(val or 0)
        sign = '+' if f >= 0 else '-'
        return f"{sign}{abs(f):>10,.2f} $"
    except (TypeError, ValueError):
        return f"+{0.0:>10,.2f} $"


def opt_detail(row) -> str:
    """Gibt PutCall/Strike/Expiry als kurzen String zurück."""
    parts = []
    if row.get('putCall'):
        parts.append(str(row['putCall']))
    strike = row.get('strike')
    if strike and pd.notna(strike) and float(strike) > 0:
        parts.append(str(int(float(strike))))
    expiry = row.get('expiry')
    if expiry and pd.notna(expiry):
        try:
            parts.append(pd.to_datetime(expiry).strftime('%d.%m.%y'))
        except Exception:
            pass
    return ' '.join(parts)


def load_data(env: str, prefix: str, campaign_id: int | None) -> pd.DataFrame:
    """Lädt campaign_ledger + trading_campaigns aus der DB."""
    engine = get_engine(env)
    ledger_table    = f"{prefix}{TABLE_CAMPAIGN_LEDGER}"
    campaigns_table = f"{prefix}{TABLE_TRADING_CAMPAIGNS}"
    where_campaign  = f"AND l.campaign_id = {campaign_id}" if campaign_id else ""

    sql = text(f"""
        SELECT
            l.id, l.campaign_id, l.dateTime, l.action,
            l.assetCategory, l.symbol, l.buySell,
            l.putCall, l.strike, l.expiry, l.tradePrice,
            l.inventory_delta, l.netcash, l.proceeds,
            l.commission, l.realized_pnl, l.linkID,
            c.name     AS campaign_name,
            c.symbol   AS campaign_symbol,
            c.status   AS campaign_status,
            c.strategy AS campaign_strategy
        FROM {ledger_table} l
        JOIN {campaigns_table} c ON c.id = l.campaign_id
        WHERE l.environment = :env
          {where_campaign}
        ORDER BY l.campaign_id, l.dateTime, l.id
    """)

    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params={'env': env})


def print_day_block(day_df: pd.DataFrame, date_str: str) -> None:
    """Gibt einen formatierten Tages-Block für einen Tag aus."""
    print(f"\n  \U0001f4c5  {date_str}")
    print(f"  \u250c{'─' * WIDTH}\u2510")

    premium_open    = 0.0
    settlement_cash = 0.0
    total_comm      = 0.0
    total_pnl       = 0.0

    for _, row in day_df.iterrows():
        action   = row.get('action', '')
        label    = ACTION_LABELS.get(action, (str(action) + '       ')[:7])
        time_str = pd.to_datetime(row['dateTime']).strftime('%H:%M')
        bs       = (str(row.get('buySell') or '') + '    ')[:4]
        detail   = opt_detail(row)[:24].ljust(24)

        if action == 'CASH_SETTLEMENT':
            cash = float(row.get('proceeds') or 0)
            settlement_cash += cash
        else:
            cash = float(row.get('netcash') or 0)
            if action in ('TRADE_OPEN', 'TRADE_CLOSE_FULL', 'TRADE_CLOSE_PARTIAL'):
                premium_open += cash

        total_comm += float(row.get('commission') or 0)
        total_pnl  += float(row.get('realized_pnl') or 0)

        cash_str = fmt_cash(cash)
        print(f"  \u2502 {time_str}  {label}  {bs}  {detail}  {cash_str}  \u2502")

    # Trennlinie
    print(f"  \u251c{'─' * WIDTH}\u2524")

    # Zusammenfassung
    # Hinweis: premium_open basiert auf netcash (Kommission bereits enthalten)
    # → total_comm NICHT nochmals zum Netto addieren (würde doppelt zählen)
    netto    = premium_open + settlement_cash
    ok       = '\u2713' if netto >= 0 else '\u2717'
    pnl_netto = total_pnl + total_comm
    pnl_ok   = '\u2713' if pnl_netto >= 0 else '\u2717'

    print(f"  \u2502  {'Netto-Prämie (Open):':<{_SUMMARY_LABEL_W}} {fmt_cash(premium_open)}  \u2502")
    if abs(settlement_cash) > 0.001:
        print(f"  \u2502  {'Settlement:':<{_SUMMARY_LABEL_W}} {fmt_cash(settlement_cash)}  \u2502")
    print(f"  \u2502  {'Netto (Cashflow):':<{_SUMMARY_LABEL_W - 2}} {ok} {fmt_cash(netto)}  \u2502")
    print(f"  \u2502  {'  davon Kommission (in Cashflow):':<{_SUMMARY_LABEL_W}} {fmt_cash(total_comm)}  \u2502")
    print(f"  \u251c{'─' * WIDTH}\u2524")
    print(f"  \u2502  {'realized_pnl (Brutto, proceeds-Basis):':<{_SUMMARY_LABEL_W}} {fmt_cash(total_pnl)}  \u2502")
    print(f"  \u2502  {'realized_pnl + Komm:':<{_SUMMARY_LABEL_W - 2}} {pnl_ok} {fmt_cash(pnl_netto)}  \u2502")
    print(f"  \u2514{'─' * WIDTH}\u2518")


def print_campaign(camp_id: int, camp_df: pd.DataFrame) -> None:
    """Gibt eine vollständige Kampagne aus."""
    symbol   = camp_df['campaign_symbol'].iloc[0]
    name     = camp_df['campaign_name'].iloc[0]
    status   = camp_df['campaign_status'].iloc[0]
    strategy = camp_df['campaign_strategy'].iloc[0] or ''

    line = '\u2550' * 62
    print(f"\n{line}")
    print(f"  KAMPAGNE: {symbol}  [ID: {camp_id}]  {strategy}  Status: {status}")
    print(f"  {name}")
    print(f"{line}")

    camp_df = camp_df.copy()
    camp_df['date_key'] = pd.to_datetime(camp_df['dateTime']).dt.strftime('%Y-%m-%d')

    for date_key, day_df in camp_df.groupby('date_key'):
        dt       = pd.to_datetime(date_key)
        wday     = DE_DAYS[dt.weekday()]
        date_fmt = f"{wday}, {dt.strftime('%d.%m.%Y')}"
        print_day_block(day_df, date_fmt)


def analyze(env: str, prefix: str, campaign_id: int | None) -> None:
    """Hauptfunktion: lädt Daten und gibt Analyse aus."""
    print(f"\nEnvironment: {env} | Prefix: '{prefix}'")
    print("Lade Daten ...")

    df = load_data(env, prefix, campaign_id)

    if df.empty:
        print("Keine Daten gefunden.")
        return

    for cid, camp_df in df.groupby('campaign_id'):
        print_campaign(int(cid), camp_df)

    # Gesamtzusammenfassung
    total_campaigns = df['campaign_id'].nunique()
    total_pnl       = df['realized_pnl'].astype(float).sum()
    total_comm      = df['commission'].astype(float).sum()
    netto           = total_pnl + total_comm

    line = '─' * 62
    print(f"\n{line}")
    print(f"  GESAMT: {total_campaigns} Kampagnen")
    print(f"  Realisierter PnL: {fmt_cash(total_pnl)}")
    print(f"  Kommissionen:     {fmt_cash(total_comm)}")
    print(f"  Netto:            {fmt_cash(netto)}")
    print(f"{line}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Analyse von 0DTE Spreads in campaign_ledger',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python src/analyze_spreads.py autom_paper
  python src/analyze_spreads.py autom_paper --user mike_
  python src/analyze_spreads.py autom_paper --campaign 42
        """,
    )
    parser.add_argument(
        'environment',
        choices=['money', 'paper', 'test', 'autom_money', 'autom_paper'],
        help='Environment'
    )
    parser.add_argument(
        '--user', default=TABLE_PREFIX, metavar='PREFIX',
        help=f'Table-Prefix (Standard: "{TABLE_PREFIX}" aus .env)'
    )
    parser.add_argument(
        '--campaign', type=int, default=None, metavar='ID',
        help='Nur diese Kampagnen-ID analysieren'
    )
    args = parser.parse_args()
    analyze(args.environment, args.user, args.campaign)


if __name__ == '__main__':
    main()
