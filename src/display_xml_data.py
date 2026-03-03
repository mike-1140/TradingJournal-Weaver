import xml.etree.ElementTree as ET
import pandas as pd
from utils.path_utils import get_project_root
import os
import sys
import streamlit as st

# Projekt-Root (Ordner über "src") dem Suchpfad hinzufügen
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# XML-Datei einlesen
INPUT_DIR = get_project_root() / "input"
file_name = "SPY.xml"

tree = ET.parse(os.path.join(INPUT_DIR, file_name))  # Pfad anpassen
root = tree.getroot()

# Alle Trade-Elemente finden
trades = root.findall(".//Trade")

# Welche Attribute sollen angezeigt werden?
wanted_attributes = [
    "symbol",
    "conid",
    "tradeID",

    "openDateTime", "holdingPeriodDateTime", "whenRealized",
    "whenReopened", "levelOfDetail", "changeInPrice", "changeInQuantity",
    "orderType", "traderID", "isAPIOrder", "accruedInt", "initialInvestment",
    "serialNumber", "deliveryType", "commodityType", "fineness", "weight",
    "positionActionID"
    
    "orderTime",

    "multiplier",
    "strike",
    "dateTime",
    "transactionType",
    "quantity",
    "tradePrice",
    "netCash",
    "buySell",
    "ibCommission",
    "proceeds"
]

rows = []
for trade in trades:
    row = {attr: trade.get(attr, "") for attr in wanted_attributes}
    rows.append(row)

# DataFrame erstellen
df = pd.DataFrame(rows, columns=wanted_attributes).transpose()
# Index (Attributnamen) in eine Spalte verschieben
df.reset_index(inplace=True)
df.rename(columns={"index": "Attribute"}, inplace=True)

# ==== Streamlit UI ====
st.set_page_config(page_title="Trades Übersicht", layout="wide")
st.title(f"📊 Trades Übersicht ")
st.write(f"{file_name}")

# # Filter: Symbol auswählen
# symbols = df["symbol"].unique().tolist()
# selected_symbols = st.multiselect("Symbol filtern", symbols, default=symbols)
#
# # Tabelle anzeigen
# filtered_df = df[df["symbol"].isin(selected_symbols)]
# st.dataframe(filtered_df, width='stretch')
st.dataframe(df, width='stretch')

# Anzahl Trades anzeigen
# st.write(f"Anzahl Trades: {len(filtered_df)}")
st.write(f"Anzahl Trades: {len(df)}")

# df.to_html("trades.html", index=False)
