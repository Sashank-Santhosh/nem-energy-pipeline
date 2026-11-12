import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from dashboard import ui

st.set_page_config(page_title="NEM Grid Pulse", layout="wide")
st.title("How is Australia's electricity grid changing?")
st.markdown(
    "A live, self-updating look at the National Electricity Market (NEM), built from AEMO's "
    "public 5-minute data. Two pages:\n\n"
    "- **Solar and the grid**: how rooftop and large-scale solar are reshaping demand and prices.\n"
    "- **Forecast accuracy**: my day-ahead demand forecast, scored against AEMO's own."
)
ui.footer(ui.connection())
