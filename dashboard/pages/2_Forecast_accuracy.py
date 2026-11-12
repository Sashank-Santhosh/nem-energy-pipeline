import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard import data, ui

st.title("How good is my forecast?")
st.markdown("Every day at 13:00 NEM time the model forecasts demand for each half-hour of the "
            "next day. It is scored against what actually happened, alongside AEMO's own "
            "pre-dispatch forecast and a naive 'same time last week' baseline.")
con = ui.connection()
region = ui.region_picker("NSW1")

latest = data.latest_interval(con)
for label, day in (("Tomorrow", (latest + pd.Timedelta(days=1)).date()),
                   ("Yesterday", (latest - pd.Timedelta(days=1)).date())):
    df = data.forecast_vs_aemo(con, region, day)
    st.subheader(f"{label}: {day:%a %d %b}")
    if df.empty:
        st.info("No forecast for this day yet.")
        continue
    df = df.rename(columns={"model_mw": "My forecast", "aemo_mw": "AEMO forecast",
                            "actual_mw": "Actual"})
    st.plotly_chart(px.line(df, x="target_time", y=["My forecast", "AEMO forecast", "Actual"],
                            labels={"value": "Demand (MW)", "target_time": "", "variable": ""}),
                    use_container_width=True)

st.subheader("Accuracy (lower is better)")
acc = data.accuracy_table(con)
if acc.empty:
    st.info("Accuracy appears once forecasts have been scored against a full day of actuals.")
else:
    st.dataframe(acc.round(2), hide_index=True, use_container_width=True)
st.caption("MAE is the average error in MW; MAPE is the average error as a percentage. The backtest "
           "uses archived short-lead weather forecasts, so it is slightly optimistic; the live "
           "30-day score is the honest number.")

ui.footer(con)
