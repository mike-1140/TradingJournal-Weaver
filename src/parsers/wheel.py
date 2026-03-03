from decimal import Decimal


def process_trades_chronologically(trades):
    """
    trades: Liste von Tuples/Dicts (qty, price, net_cash)
    """
    open_tranches = []  # Hier speichern wir Datensätze mit {qty, price, net_cash}

    for trade in trades:
        t_qty = Decimal(str(trade['qty']))
        t_price = Decimal(str(trade['price']))
        t_cash = Decimal(str(trade['net_cash']))

        print(f"\n--- Verarbeite Trade: {t_qty} @ {t_price} ---")

        # FALL 1: Zukauf oder Eröffnung (Gleiche Richtung oder Lager leer)
        # Wir prüfen, ob die neue Menge die bestehende Position verstärkt oder neu beginnt
        current_inventory = sum(tr['qty'] for tr in open_tranches)

        if current_inventory == 0 or (current_inventory * t_qty > 0):
            open_tranches.append({
                'qty': t_qty,
                'price': t_price,
                'net_cash': t_cash
            })
            print(f"Zukauf gebucht. Lagerbestand: {sum(tr['qty'] for tr in open_tranches)}")

        # FALL 2: Verkauf / Schließung (Gegenrichtung)
        else:
            remaining_to_close = t_qty  # Die Menge, die wir "verrechnen" müssen

            while remaining_to_close != 0 and open_tranches:
                # Nimm die älteste Tranche (FIFO)
                oldest = open_tranches[0]

                # Prüfe, ob die älteste Tranche den Verkauf komplett schluckt
                if abs(oldest['qty']) > abs(remaining_to_close):
                    # SPLIT: Tranche ist größer als der Verkauf
                    used_ratio = abs(remaining_to_close / oldest['qty'])

                    # Proportionale Werte für den Teil, der übrig bleibt
                    oldest['qty'] += remaining_to_close
                    oldest['net_cash'] *= (1 - used_ratio)

                    print(f"Tranche teilweise geschlossen. Rest in Tranche: {oldest['qty']}")
                    remaining_to_close = 0
                else:
                    # FULL CLOSE: Tranche wird komplett aufgebraucht
                    remaining_to_close += oldest['qty']
                    open_tranches.pop(0)  # Aus dem Lager entfernen
                    print(f"Tranche vollständig geschlossen. Restmenge zum Verrechnen: {remaining_to_close}")

            # FALL 3: Overbought / Oversold (Dreher)
            # Wenn nach dem Leeren des Lagers noch Menge übrig ist
            if remaining_to_close != 0:
                open_tranches.append({
                    'qty': remaining_to_close,
                    'price': t_price,
                    'net_cash': (remaining_to_close / t_qty) * t_cash  # Proportionaler Cashflow
                })
                print(f"Position gedreht! Neue Tranche (Gegenrichtung): {remaining_to_close}")

    return open_tranches


# --- TESTLAUF ---
test_sequence = [
    {'qty': 50, 'price': 10, 'net_cash': -500},
    {'qty': 30, 'price': 11, 'net_cash': -330},
    {'qty': 70, 'price': 12, 'net_cash': -840},  # Bestand: 150
    {'qty': -30, 'price': 13, 'net_cash': 390},  # Schließt 30 von den ersten 50 -> Rest 20, 30, 70
    {'qty': -60, 'price': 14, 'net_cash': 840},  # Schließt die restlichen 20 und 30 sowie 10 von den 70 -> Rest 60
    {'qty': -90, 'price': 15, 'net_cash': 1350}  # Schließt die restlichen 60 -> Dreher auf -30
]

final_inventory = process_trades_chronologically(test_sequence)
print(f"\nFINALES ERGEBNIS: {sum(tr['qty'] for tr in final_inventory)} (Sollte -30 sein)")