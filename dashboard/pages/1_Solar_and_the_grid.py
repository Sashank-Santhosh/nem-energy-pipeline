import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import plotly.express as px
import streamlit as st

from dashboard import data, ui

st.title("How is rooftop solar changing the grid?")
con = ui.connection()
region = ui.region_picker()

cards = data.headline_cards(con, region)
c1, c2, c3 = st.columns(3)
today, year_ago = cards["min_demand_today"], cards["min_demand_year_ago"]
delta = None if today is None or year_ago is None else f"{today - year_ago:,.0f} MW vs a year ago"
c1.metric("Lowest demand yesterday", ui.fmt(today, "{:,.0f} MW"), delta, delta_color="off")
c2.metric("Negative-price intervals this month",
          ui.fmt(cards["negative_intervals_month"], "{:,.0f}"))
c3.metric("Solar share at midday (last 7 days)", ui.fmt(cards["midday_solar_share"], "{:.0%}"))

latest = data.latest_interval(con)
curve = data.duck_curve(con, region, latest.date().replace(day=1)).rename(
    columns={"this_year_mw": "This year", "last_year_mw": "Same month last year"})
fig = px.line(curve, x="time_of_day", y=["This year", "Same month last year"],
              labels={"value": "Average demand (MW)", "time_of_day": "Time of day", "variable": ""})
st.plotly_chart(fig, use_container_width=True)
st.caption("The 'duck curve': demand from the grid sags at midday as rooftop panels supply homes "
           "directly, then climbs steeply into the evening when the sun sets.")

neg = data.negative_price_counts(con)
st.plotly_chart(px.bar(neg, x="month", y="intervals", color="regionid", barmode="group",
                       labels={"intervals": "5-minute intervals below $0/MWh", "month": ""}),
                use_container_width=True)
st.caption("Negative prices happen when there is more cheap solar and wind than the grid needs; "
           "generators pay to keep running rather than switch off.")

mix = data.fuel_mix_by_hour(con, region)
st.plotly_chart(px.area(mix, x="hour", y="mw", color="fuel",
                        labels={"mw": "Average output (MW)", "hour": "Hour of day"}),
                use_container_width=True)
st.caption("Where the electricity comes from at each hour of the day, averaged over the last 30 days.")

ui.footer(con)
