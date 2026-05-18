"""
Parst IBKR Activity Statement CSV (englisches Format) in strukturierte Snapshot-Daten.
"""

import csv
from collections import defaultdict
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional


class ActivityCsvParser:
    """
    Liest eine IBKR Activity Statement CSV und extrahiert daraus
    alle Felder für einen account_snapshots-Eintrag.

    Verwendung:
        parser = ActivityCsvParser("U12345_20260513.csv")
        snapshot = parser.snapshot   # Dict, direkt in DB einfügbar
    """

    def __init__(self, filepath: str | Path):
        self.filepath = Path(filepath)
        self._sections: dict[str, list] = {}
        self.snapshot: dict = {}
        self.account_id: str | None = None
        self._parse_file()
        self._extract_snapshot()
        self.account_id = self._extract_account_id()

    # ------------------------------------------------------------------
    # Datei-Parsing
    # ------------------------------------------------------------------

    def _parse_file(self):
        """Liest CSV und gruppiert alle Zeilen nach Sektionsname."""
        sections = defaultdict(list)
        with open(self.filepath, newline='', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) < 2:
                    continue
                section = row[0].strip()
                row_type = row[1].strip()
                data = row[2:]
                sections[section].append({'type': row_type, 'data': data})
        self._sections = dict(sections)

    def _section_as_records(self, section_name: str) -> list[dict]:
        """
        Gibt Data-Zeilen einer Sektion als Liste von Dicts zurück.
        Der zuletzt gesehene Header (mit mind. 2 Spalten) bestimmt das Mapping.
        """
        rows = self._sections.get(section_name, [])
        headers: list[str] | None = None
        result = []
        for row in rows:
            if row['type'] == 'Header' and len(row['data']) > 1:
                headers = [col.strip() for col in row['data']]
            elif row['type'] == 'Data' and headers:
                record = dict(zip(headers, row['data']))
                result.append(record)
        return result

    def _section_as_kv(self, section_name: str) -> dict[str, str]:
        """
        Gibt Key-Value-Sektionen als Dict zurück (z.B. Statement, Change in NAV).
        Jede Data-Zeile: [key, value, ...]
        """
        rows = self._sections.get(section_name, [])
        result = {}
        for row in rows:
            if row['type'] == 'Data' and len(row['data']) >= 2:
                key = row['data'][0].strip()
                value = row['data'][1].strip()
                result[key] = value
        return result

    # ------------------------------------------------------------------
    # Typ-Konvertierung
    # ------------------------------------------------------------------

    @staticmethod
    def _to_decimal(value: str | None) -> Optional[Decimal]:
        if not value or str(value).strip() in ('--', '', 'N/A'):
            return None
        clean = str(value).strip().replace('%', '').replace(',', '')
        try:
            return Decimal(clean)
        except InvalidOperation:
            return None

    @staticmethod
    def _parse_period_date(value: str) -> Optional[date]:
        """Parst 'May 13, 2026' oder '2026-05-13' zu einem date-Objekt."""
        for fmt in ('%B %d, %Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
        return None

    # ------------------------------------------------------------------
    # Snapshot-Extraktion
    # ------------------------------------------------------------------

    def _extract_snapshot(self):
        snapshot_date = self._extract_date()
        nav_prior, nav_current, nav_change, twrr = self._extract_nav()
        starting_value, mtm_pnl, commissions_eur, ending_value = self._extract_nav_change()
        cash_eur, cash_usd, forex_translation_pnl = self._extract_cash()
        realized_pnl, unrealized_pnl = self._extract_pnl()
        mtd_pnl, ytd_pnl = self._extract_mtd_ytd()

        self.snapshot = {
            'snapshot_date':        snapshot_date,
            'nav_prior':            nav_prior,
            'nav_current':          nav_current,
            'nav_change':           nav_change,
            'twrr':                 twrr,
            'starting_value':       starting_value,
            'mtm_pnl':              mtm_pnl,
            'commissions_eur':      commissions_eur,
            'ending_value':         ending_value,
            'cash_eur':             cash_eur,
            'cash_usd':             cash_usd,
            'forex_translation_pnl': forex_translation_pnl,
            'realized_pnl_eur':     realized_pnl,
            'unrealized_pnl_eur':   unrealized_pnl,
            'mtd_pnl':              mtd_pnl,
            'ytd_pnl':              ytd_pnl,
            'imported_at':          datetime.now(),
        }

    def _extract_account_id(self) -> str | None:
        kv = self._section_as_kv('Account Information')
        value = kv.get('Account')
        return value if value else None

    def _extract_date(self) -> Optional[date]:
        stmt_kv = self._section_as_kv('Statement')
        return self._parse_period_date(stmt_kv.get('Period', ''))

    def _extract_nav(self) -> tuple:
        records = self._section_as_records('Net Asset Value')
        total_row = next(
            (r for r in records if r.get('Asset Class', '').strip() == 'Total'),
            None
        )
        nav_prior   = self._to_decimal(total_row.get('Prior Total'))   if total_row else None
        nav_current = self._to_decimal(total_row.get('Current Total')) if total_row else None
        nav_change  = self._to_decimal(total_row.get('Change'))        if total_row else None

        # TWRR steht in einer Sonder-Data-Zeile mit genau einem Wert (z.B. "3.07820186%")
        twrr = None
        for row in self._sections.get('Net Asset Value', []):
            if row['type'] == 'Data' and len(row['data']) == 1 and '%' in row['data'][0]:
                twrr = self._to_decimal(row['data'][0])
                break

        return nav_prior, nav_current, nav_change, twrr

    def _extract_nav_change(self) -> tuple:
        kv = self._section_as_kv('Change in NAV')
        return (
            self._to_decimal(kv.get('Starting Value')),
            self._to_decimal(kv.get('Mark-to-Market')),
            self._to_decimal(kv.get('Commissions')),
            self._to_decimal(kv.get('Ending Value')),
        )

    def _extract_cash(self) -> tuple:
        records = self._section_as_records('Cash Report')

        def find(label: str, currency: str) -> Optional[Decimal]:
            row = next(
                (r for r in records
                 if r.get('Currency Summary', '').strip() == label
                 and r.get('Currency', '').strip() == currency),
                None
            )
            return self._to_decimal(row.get('Total')) if row else None

        cash_eur = find('Ending Cash', 'EUR')
        cash_usd = find('Ending Cash', 'USD')
        forex_pnl = find('Cash FX Translation Gain/Loss', 'Base Currency Summary')
        return cash_eur, cash_usd, forex_pnl

    def _extract_pnl(self) -> tuple:
        records = self._section_as_records('Realized & Unrealized Performance Summary')
        total_row = next(
            (r for r in records if r.get('Asset Category', '').strip() == 'Total (All Assets)'),
            None
        )
        realized   = self._to_decimal(total_row.get('Realized Total'))   if total_row else None
        unrealized = self._to_decimal(total_row.get('Unrealized Total')) if total_row else None
        return realized, unrealized

    def _extract_mtd_ytd(self) -> tuple:
        records = self._section_as_records('Month & Year to Date Performance Summary')
        total_row = next(
            (r for r in records if r.get('Asset Category', '').strip() == 'Total (All Assets)'),
            None
        )
        mtd = self._to_decimal(total_row.get('Realized S/T MTD')) if total_row else None
        ytd = self._to_decimal(total_row.get('Realized S/T YTD')) if total_row else None
        return mtd, ytd
