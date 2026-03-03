"""
ACB (Adjusted Cost Basis) Calculator für Wheel-Trading Strategie
Zentrale Logik für alle ACB-Berechnungen
"""
from typing import Dict, Any, Optional
from src.logger_setup import setup_logging
from src.utils.path_utils import get_project_root

# Get logger - use the same logger name across all files
log_file = get_project_root() / "log/app.log"
logger, _ = setup_logging('my_app', level="simple", log_file=log_file)


class ACBCalculator:
    """Zentrale Klasse für Adjusted Cost Basis Berechnungen"""

    MIN_ACB = 0.01  # Minimum ACB um negative Werte zu vermeiden
    MIN_QUANTITY = 0.0001  # Minimum Quantity für Berechnungen

    # @staticmethod
    # def calculate_acb(trade: Dict[str, Any], total_premiums: float) -> float:
    #     """
    #     Berechnet die Adjusted Cost Basis für einen Trade unter Berücksichtigung
    #     der Wheel-Strategie Prämien
    #
    #     Args:
    #         trade: Trade Dictionary mit tradePrice, quantity, assetCategory
    #         total_premiums: Summe aller bisher gesammelten Prämien im Wheel
    #
    #     Returns:
    #         Adjusted Cost Basis per Aktie/Kontrakt
    #
    #     Raises:
    #         ValueError: Bei ungültiger Quantity
    #     """
    #     qty = abs(trade['quantity'])
    #
    #     # Validierung
    #     if qty < ACBCalculator.MIN_QUANTITY:
    #         raise ValueError(
    #             f"Ungültige Quantity für Trade {trade.get('symbol', 'UNKNOWN')}: {qty}"
    #         )
    #
    #     trade_price = trade['tradePrice']
    #     asset_category = trade['assetCategory']
    #
    #     if asset_category == 'STK':
    #         # AKTIEN: Kaufpreis minus gesammelte Prämien, verteilt auf alle Aktien
    #         # Formel: (|Preis * Menge| - Prämien) / |Menge|
    #         raw_acb = (abs(trade_price * qty) - total_premiums) / qty
    #
    #         logger.debug(
    #             f"ACB Stock [{trade.get('symbol')}]: "
    #             f"Price={trade_price:.2f}, Qty={qty:.0f}, "
    #             f"Premiums={total_premiums:.2f} => Raw ACB={raw_acb:.4f}"
    #         )
    #     else:
    #         # OPTIONEN: Strike/Premium minus Roll-Gewinne pro Kontrakt
    #         # Formel: Preis - (Prämien / Menge)
    #         raw_acb = trade_price - (total_premiums / qty)
    #
    #         logger.debug(
    #             f"ACB Option [{trade.get('symbol')}]: "
    #             f"Price={trade_price:.2f}, Qty={qty:.0f}, "
    #             f"Premiums={total_premiums:.2f} => Raw ACB={raw_acb:.4f}"
    #         )
    #
    #     # Validierung und Korrektur negativer ACB
    #     return ACBCalculator.validate_acb(raw_acb, trade.get('symbol', 'UNKNOWN'))

    @staticmethod
    def calculate_acb(trade: Dict[str, Any], total_premiums: float) -> float:
        """
        Berechnet die Adjusted Cost Basis (Bonus-Logik).
        Zieht gesammelte Prämien vom Preis ab, um den Break-Even zu ermitteln.
        """
        qty = abs(trade['quantity'])

        # Validierung der Menge
        if qty < ACBCalculator.MIN_QUANTITY:
            raise ValueError(
                f"Ungültige Quantity für Trade {trade.get('symbol', 'UNKNOWN')}: {qty}"
            )

        trade_price = trade['tradePrice']
        asset_category = trade['assetCategory']

        if asset_category == 'STK':
            # AKTIEN: (Kaufpreis * Menge - alle Prämien) / Menge
            # Dies ist dein "Bonus-Preis" pro Aktie.
            raw_acb = (abs(trade_price * qty) - total_premiums) / qty

            logger.debug(f"ACB Stock Bonus [{trade.get('symbol')}]: "
                         f"Basis: {trade_price:.2f} -> Adj: {raw_acb:.4f}")

        else:
            # OPTIONEN: (Strike/Premium - (Bisherige Gewinne / Menge))
            # Wenn du einen Call bei 100 verkaufst und schon 5.00 Bonus hast,
            # ist dein Break-Even bei 105.00 (für Short Calls).

            # Bei Short-Optionen (quantity < 0) wirken Prämien als Puffer
            if trade.get('quantity', 0) < 0:
                # Wir addieren/subtrahieren je nach Richtung, um den
                # effektiven Break-Even des Trades zu sehen.
                raw_acb = trade_price + (total_premiums / qty)
            else:
                # Bei Rückkäufen (Buy to Close) bleibt es meist beim Preis
                raw_acb = trade_price

        # Validierung (verhindert negative Werte falls gewünscht)
        return ACBCalculator.validate_acb(raw_acb, trade.get('symbol', 'UNKNOWN'))

    @staticmethod
    def calculate_weighted_average_acb(
            old_qty: float,
            old_acb: float,
            new_qty: float,
            new_acb: float
    ) -> float:
        """
        Berechnet gewichteten Durchschnitt der ACB beim Aufstocken einer Position

        Args:
            old_qty: Bisherige Quantity (absolut)
            old_acb: Bisherige ACB
            new_qty: Neue Quantity (absolut)
            new_acb: Neue ACB

        Returns:
            Gewichtete durchschnittliche ACB

        Raises:
            ValueError: Bei ungültiger Gesamt-Quantity
        """
        old_qty = abs(old_qty)
        new_qty = abs(new_qty)
        total_qty = old_qty + new_qty

        if total_qty < ACBCalculator.MIN_QUANTITY:
            raise ValueError(f"Ungültige Gesamt-Quantity: {total_qty}")

        # Gewichteter Durchschnitt: (Menge1 * ACB1 + Menge2 * ACB2) / Gesamt-Menge
        old_total_cost = old_qty * old_acb
        new_total_cost = new_qty * new_acb
        weighted_acb = (old_total_cost + new_total_cost) / total_qty

        logger.debug(
            f"Weighted Average ACB: "
            f"Old({old_qty:.0f} @ {old_acb:.4f}) + New({new_qty:.0f} @ {new_acb:.4f}) "
            f"= {weighted_acb:.4f}"
        )

        return ACBCalculator.validate_acb(weighted_acb, "weighted_average")

    @staticmethod
    def adjust_acb_for_split(acb: float, split_multiplier: float, symbol: str) -> float:
        """
        Passt ACB für Stock Splits an

        Args:
            acb: Aktuelle ACB
            split_multiplier: Split-Multiplikator (z.B. 2.0 für 2:1 Split)
            symbol: Symbol für Logging

        Returns:
            Angepasste ACB
        """
        if abs(split_multiplier - 1.0) < 0.0001:
            return acb

        adjusted_acb = acb / split_multiplier

        logger.info(
            f"ACB Split Adjustment [{symbol}]: "
            f"{acb:.4f} / {split_multiplier:.2f} = {adjusted_acb:.4f}"
        )

        return ACBCalculator.validate_acb(adjusted_acb, symbol)

    @staticmethod
    def validate_acb(acb: float, symbol: str) -> float:
        if acb < 0:
            # Ein negativer Wert bedeutet: Dein Profit aus Prämien ist
            # größer als die Kosten der aktuellen Position.
            logger.info(f"💰 Bonus-Maximum erreicht für {symbol}: Position ist kostenfrei.")
            return 0.00
        return acb

    @staticmethod
    def transfer_acb_to_trade(
            target_trade: Dict[str, Any],
            source_acb: Optional[float],
            fallback_price: Optional[float] = None
    ) -> None:
        """
        Überträgt ACB von einer Position zur anderen (mutiert target_trade)

        Args:
            target_trade: Ziel-Trade Dictionary (wird modifiziert)
            source_acb: Quell-ACB (kann None sein)
            fallback_price: Fallback wenn source_acb None ist
        """
        if source_acb is not None:
            target_trade['adj_cost_basis'] = source_acb
        elif fallback_price is not None:
            target_trade['adj_cost_basis'] = fallback_price
            logger.debug(f"ACB fallback to trade price: {fallback_price:.4f}")
        else:
            logger.warning(
                f"Keine ACB verfügbar für {target_trade.get('symbol', 'UNKNOWN')}"
            )
