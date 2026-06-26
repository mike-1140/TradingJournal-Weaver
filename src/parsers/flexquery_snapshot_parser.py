"""
Parst IBKR FlexQuery Activity XML (type AF) in account_snapshots-Daten.
Jedes <FlexStatement> im XML entspricht einem Snapshot-Tag.
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional
from xml.etree import ElementTree as ET


def _d(value) -> Optional[Decimal]:
    if value is None or str(value).strip() == '':
        return None
    try:
        return Decimal(str(value).strip())
    except InvalidOperation:
        return None


def _d0(value) -> Decimal:
    return _d(value) or Decimal('0')


def _parse_date(raw: str) -> Optional[date]:
    for fmt in ('%d/%m/%Y', '%Y%m%d', '%Y-%m-%d'):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


class FlexquerySnapshotParser:
    """
    Parst den Inhalt einer IBKR Activity-Flex-XML (type="AF").
    Gibt eine Liste von Snapshot-Dicts zurück — eines pro FlexStatement-Tag.

    Hinweise zu Feldern:
    - twrr:             Modified Dietz (exakt bei keinen Transfers, sonst Näherung)
    - unrealized_pnl_eur: Absoluter Marktwert offener Positionen (OPT+STK), nicht P&L vs Einstand
    - mtd_pnl/ytd_pnl:  Näherung via CashReport-Kumulativfelder (Sales+Purchases+Commissions);
                        weicht von FIFO-P&L ab wenn offene Positionen im Monat vorhanden
    """

    def __init__(self, xml_content: str):
        self._root = ET.fromstring(xml_content)
        self.snapshots: list[dict] = self._parse_all()

    def _parse_all(self) -> list[dict]:
        result = []
        for stmt in self._root.findall('.//FlexStatement'):
            snap = self._parse_statement(stmt)
            if snap:
                result.append(snap)
        return result

    def _parse_statement(self, stmt) -> Optional[dict]:
        account_id    = stmt.get('accountId', '').strip()
        snapshot_date = _parse_date(stmt.get('toDate', ''))
        if not snapshot_date or not account_id:
            return None

        nav_prior, nav_current = self._equity_nav(stmt, snapshot_date)
        nav_change = (nav_current - nav_prior) if (nav_prior and nav_current) else None

        cash_base     = stmt.find('.//CashReportCurrency[@currency="BASE_SUMMARY"]')
        cash_eur_elem = stmt.find('.//CashReportCurrency[@currency="EUR"]')
        cash_usd_elem = stmt.find('.//CashReportCurrency[@currency="USD"]')

        commissions_eur = _d(cash_base.get('commissions'))            if cash_base is not None else None
        forex_pnl       = _d(cash_base.get('fxTranslationGainLoss')) if cash_base is not None else None
        deposits        = _d0(cash_base.get('depositWithdrawals', '0')) if cash_base is not None else Decimal('0')
        cash_eur        = _d(cash_eur_elem.get('endingCash'))         if cash_eur_elem is not None else None
        cash_usd        = _d(cash_usd_elem.get('endingCash'))         if cash_usd_elem is not None else None

        return {
            'account_id':            account_id,
            'snapshot_date':         snapshot_date,
            'nav_prior':             nav_prior,
            'nav_current':           nav_current,
            'nav_change':            nav_change,
            'twrr':                  self._twrr(nav_prior, nav_current, deposits),
            'starting_value':        nav_prior,
            'mtm_pnl':               self._mtm_total(stmt),
            'commissions_eur':       commissions_eur,
            'ending_value':          nav_current,
            'cash_eur':              cash_eur,
            'cash_usd':              cash_usd,
            'forex_translation_pnl': forex_pnl,
            'realized_pnl_eur':      self._realized_pnl(stmt),
            'unrealized_pnl_eur':    self._unrealized(stmt, snapshot_date),
            'mtd_pnl':               self._mtd_ytd(cash_base)[0],
            'ytd_pnl':               self._mtd_ytd(cash_base)[1],
            'imported_at':           datetime.now(),
        }

    def _equity_nav(self, stmt, snapshot_date: date) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """Liest Vortags- und Tages-NAV aus EquitySummaryByReportDateInBase."""
        entries = []
        for e in stmt.findall('EquitySummaryInBase/EquitySummaryByReportDateInBase'):
            d = _parse_date(e.get('reportDate', ''))
            if d:
                entries.append((d, _d(e.get('total'))))
        entries.sort(key=lambda x: x[0])

        nav_prior = nav_current = None
        for d, total in entries:
            if d < snapshot_date:
                nav_prior = total
            elif d == snapshot_date:
                nav_current = total
        return nav_prior, nav_current

    def _mtm_total(self, stmt) -> Optional[Decimal]:
        """Tages-MTM-P&L aus der Summenzeile von MTMPerformanceSummaryInBase."""
        for elem in stmt.findall('.//MTMPerformanceSummaryUnderlying'):
            if elem.get('description', '') == 'Total P/L':
                return _d(elem.get('total'))
        return None

    def _realized_pnl(self, stmt) -> Decimal:
        """FIFO-P&L aller Trades des Tages in EUR (fifoPnlRealized × fxRateToBase)."""
        total = Decimal('0')
        for trade in stmt.findall('.//Trade'):
            fifo = _d(trade.get('fifoPnlRealized'))
            fx   = _d(trade.get('fxRateToBase', '1'))
            if fifo is not None and fx is not None:
                total += fifo * fx
        return total

    def _unrealized(self, stmt, snapshot_date: date) -> Optional[Decimal]:
        """Absoluter Marktwert offener OPT+STK-Positionen in EUR am Snapshot-Tag."""
        for e in stmt.findall('EquitySummaryInBase/EquitySummaryByReportDateInBase'):
            if _parse_date(e.get('reportDate', '')) == snapshot_date:
                return _d0(e.get('options', '0')) + _d0(e.get('stock', '0'))
        return None

    @staticmethod
    def _mtd_ytd(cash_base) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """
        Kumulativer MTD/YTD-P&L aus CashReport-Feldern (Sales + Purchases + Commissions).
        Näherung: enthält Prämien offener Positionen → weicht bei laufenden Trades von FIFO ab.
        """
        if cash_base is None:
            return None, None
        mtd = (_d0(cash_base.get('netTradesSalesMTD',  '0'))
             + _d0(cash_base.get('netTradesPurchasesMTD', '0'))
             + _d0(cash_base.get('commissionsMTD', '0')))
        ytd = (_d0(cash_base.get('netTradesSalesYTD',  '0'))
             + _d0(cash_base.get('netTradesPurchasesYTD', '0'))
             + _d0(cash_base.get('commissionsYTD', '0')))
        return mtd, ytd

    @staticmethod
    def _twrr(nav_prior, nav_current, deposits: Decimal) -> Optional[Decimal]:
        """Modified Dietz TWRR in Prozent. Bei Deposits/Withdrawals = 0 identisch mit IBKR-CSV."""
        if not nav_prior or not nav_current or nav_prior == 0:
            return None
        if deposits != 0:
            denominator = nav_prior + Decimal('0.5') * deposits
            if denominator == 0:
                return None
            return ((nav_current - nav_prior - deposits) / denominator) * 100
        return ((nav_current - nav_prior) / nav_prior) * 100
