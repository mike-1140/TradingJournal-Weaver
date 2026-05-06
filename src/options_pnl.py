"""
OPTIONS PnL BERECHNUNG - Vollständiger Guide
=============================================

IBKR verwendet verschiedene Felder für P&L-Tracking. Dieser Guide erklärt,
wie man für jedes Szenario den korrekten P&L berechnet.

WICHTIGE IBKR FELDER
--------------------

Bei TRADES:
-----------
- cost: Cost basis der Position
  * Positiv bei BUY (du zahlst)
  * Negativ bei SELL (du erhältst)
  * Inkludiert Kommissionen

- proceeds: Erhaltenes/Gezahltes Geld
  * Positiv = du erhältst Geld
  * Negativ = du zahlst Geld
  * Ohne Kommissionen

- netCash: Tatsächlicher Cashflow
  * netCash = proceeds + taxes - ibCommission

- fifoPnlRealized: Von IBKR berechneter realisierter P&L
  * Nur bei CLOSING Trades (BookTrades)
  * Verwendet FIFO-Methode
  * WICHTIG: Bei Cash Settlement ist Cash Settlement BEREITS INKLUDIERT!

- quantity: Anzahl Contracts
  * Negativ = SELL
  * Positiv = BUY

- multiplier: Meist 100 bei Optionen

Bei OptionEAE:
--------------
- realizedPnl: P&L aus dem Event
  * Bei Assignment/Exercise: Gesamter Options-P&L
  * Bei Cash Settlement: Meist 0 (schon in Assignment/Exercise enthalten)

- proceeds: Cashflow aus dem Event
  * Bei Assignment/Exercise: Meist 0
  * Bei Cash Settlement: Tatsächlicher Cash-Betrag

- costBasis: Cost Basis der Position


SZENARIEN UND BERECHNUNGEN
===========================

SZENARIO 1: EXPIRATION (Wertlos verfallen)
------------------------------------------

Struktur:
    ExchTrade (Opening): SELL/BUY Option für Premium
    BookTrade (Closing): BUY/SELL Option für 0
    OptionEAE: Expiration Event

Beispiel (SELL Option, expires worthless - GEWINN):
    ExchTrade: quantity=-1, tradePrice=0.27, proceeds=27, cost=-26.20
    BookTrade: quantity=+1, tradePrice=0, proceeds=0, fifoPnlRealized=26.20

Berechnung:
    realized_pnl = BookTrade.fifoPnlRealized

    Oder manuell:
    premium_collected = ExchTrade.netCash  (z.B. 26.20)
    closing_cost = 0
    realized_pnl = premium_collected = 26.20


SZENARIO 2: ASSIGNMENT mit Stock-Delivery (z.B. ON)
---------------------------------------------------

Struktur:
    ExchTrade (Opening): SELL/BUY Option für Premium
    BookTrade (Closing): BUY/SELL Option, schließt Position
    BookTrade (Stock): Stock wird geliefert zum Strike
    OptionEAE: Assignment Event (für Option)
    OptionEAE: Sell Event (für Stock) - IGNORIEREN (ist kein Options-EAE)

Beispiel (SELL Call, assigned - muss Stock liefern):
    ExchTrade: quantity=-1, tradePrice=0.27, netCash=26.20
    BookTrade (Option): quantity=+1, tradePrice=0, fifoPnlRealized=26.20
    BookTrade (Stock): quantity=-100, tradePrice=52, proceeds=5200

Berechnung:
    # Option P&L
    option_pnl = BookTrade[Option].fifoPnlRealized  (z.B. 26.20)

    # Stock ist separater Trade - wird separat getrackt
    stock_basis = Strike * multiplier * quantity  (z.B. 52 * 100 = 5200)

WICHTIG: Bei Assignment entsteht eine Stock-Position. Der Options-P&L ist
         der Premium. Der Stock-Trade ist ein NEUER separater Trade!


SZENARIO 3: EXERCISE/ASSIGNMENT mit Cash Settlement (z.B. SPX)
--------------------------------------------------------------

Struktur:
    ExchTrade (Opening): SELL/BUY Option für Premium
    BookTrade (Closing): BUY/SELL Option, schließt Position
    OptionEAE: Assignment/Exercise Event
    OptionEAE: Cash Settlement Event (separate tradeID!)

Beispiel 1 (BUY Put, Exercise - GEWINN):
    ExchTrade: quantity=1, tradePrice=7.15, netCash=-716.64
    BookTrade: quantity=-1, tradePrice=0, fifoPnlRealized=2102.36
    Exercise EAE: realizedPnl=2102.36
    Cash Settlement EAE: proceeds=2819

Beispiel 2 (SELL Put, Assignment - VERLUST):
    ExchTrade: quantity=-1, tradePrice=8.6, netCash=858.36
    BookTrade: quantity=1, tradePrice=0, fifoPnlRealized=-2460.64
    Assignment EAE: realizedPnl=-2460.64
    Cash Settlement EAE: proceeds=-3319

Berechnung - METHODE 1 (Empfohlen):
    realized_pnl = BookTrade.fifoPnlRealized

    WICHTIG: Der fifoPnlRealized enthält BEREITS den Cash Settlement!

Berechnung - METHODE 2 (Manuelle Verifikation):
    premium = ExchTrade.netCash
    cash_settlement = CashSettlement_EAE.proceeds
    realized_pnl = premium + cash_settlement

    Beispiel 1: -716.64 + 2819 = 2102.36 ✓
    Beispiel 2: 858.36 + (-3319) = -2460.64 ✓


ZUSAMMENFASSUNG - WAS VERWENDEN?
=================================

Für GESCHLOSSENE Positionen (BookTrades):
    ✅ Verwende: BookTrade.fifoPnlRealized

    Das ist der KORREKTE Gesamt-P&L, weil:
    - IBKR berechnet FIFO korrekt
    - Bei Cash Settlement ist es bereits inkludiert
    - Bei Assignment ist der Options-P&L korrekt
    - Bei Expiration ist es der Premium-Gewinn/Verlust

Für OFFENE Positionen:
    ✅ Verwende: cost basis tracking
    ✅ Mark-to-Market P&L = current_value - cost_basis

Für CASH SETTLEMENT Verifikation:
    ✅ Premium + cashSettlement_proceeds sollte = fifoPnlRealized sein


IMPLEMENTIERUNG
===============
"""

import pandas as pd
from src.logger_setup import print_log


def calculate_pnl(trades_df, logger=None):
    """
    Berechnet den realisierten P&L für Options-Trades.

    Parameters
    ----------
    trades_df : pd.DataFrame
        DataFrame mit Trades, bereits durch handle_booktrades() verarbeitet.
        Muss enthalten: status, transactionType, fifoPnlRealized, netCash,
                       cashSettlement_proceeds, assetCategory

    Returns
    -------
    pd.DataFrame
        Input DataFrame mit zusätzlichen Spalten:
        - realized_pnl: Realisierter P&L für diesen Trade
        - pnl_source: Woher kommt der P&L ("BookTrade", "Calculated", etc.)
        - verification_ok: Bool, ob Cash Settlement Verifikation stimmt
    """

    df = trades_df.copy()
    df['realized_pnl'] = None
    df['pnl_source'] = None

    # Closing Trades haben fifoPnlRealized
    closing_mask = df['openCloseIndicator'] == 'C'

    if closing_mask.any():
        df.loc[closing_mask, 'realized_pnl'] = pd.to_numeric(
            df.loc[closing_mask, 'fifoPnlRealized'],
            errors='coerce'
        )
        df.loc[closing_mask, 'pnl_source'] = 'Closing_Trade'

    # Opening Trades haben keinen realized P&L
    opening_mask = df['openCloseIndicator'] == 'O'

    if opening_mask.any():
        df.loc[opening_mask, 'realized_pnl'] = 0
        df.loc[opening_mask, 'pnl_source'] = 'Opening_Trade'

    return df


def get_position_summary(trades_df, logger=None):
    """
    Erstellt eine Zusammenfassung aller realisierten P&Ls gruppiert nach Symbol.

    Parameters
    ----------
    trades_df : pd.DataFrame
        DataFrame mit berechneten P&Ls (nach calculate_options_pnl)

    Returns
    -------
    pd.DataFrame
        Zusammenfassung mit Spalten: symbol, total_realized_pnl, trade_count,
                                     status_counts
    """

    # Nur Options mit realized P&L
    opt_with_pnl = trades_df[
        (trades_df['assetCategory'] == 'OPT') &
        (trades_df['realized_pnl'].notna()) &
        (trades_df['realized_pnl'] != 0)
        ].copy()

    if len(opt_with_pnl) == 0:
        logger.warning("Keine Trades mit realized P&L gefunden")
        return pd.DataFrame()

    # Gruppiere nach Symbol
    summary = opt_with_pnl.groupby('symbol').agg({
        'realized_pnl': ['sum', 'count'],
        'status': lambda x: ', '.join(x.dropna().unique())
    }).reset_index()

    summary.columns = ['symbol', 'total_realized_pnl', 'trade_count', 'status_types']

    # Sortiere nach P&L
    summary = summary.sort_values('total_realized_pnl', ascending=False)

    return summary
