"""Shared page pieces: cached connection, region picker, freshness and credits footer."""

import pandas as pd
import streamlit as st

from dashboard import copy, data
from ingest.sources import REGIONS

REGION_NAMES = {"NSW1": "New South Wales", "QLD1": "Queensland", "VIC1": "Victoria",
                "SA1": "South Australia", "TAS1": "Tasmania"}


def fmt(value, pattern: str) -> str:
    """Format a number, or "n/a" when it is missing (never show a fake zero)."""
    if value is None or pd.isna(value):
        return "n/a"
    return pattern.format(value)


@st.cache_resource(ttl=3600)
def connection():
    return data.get_connection()


def region_picker(default: str = "SA1") -> str:
    return st.selectbox("Region", REGIONS, index=REGIONS.index(default),
                        format_func=lambda r: REGION_NAMES[r])


def footer(con) -> None:
    latest = data.latest_interval(con)
    now = pd.Timestamp.now('UTC').tz_localize(None) + pd.Timedelta(hours=10)  # NEM time
    if data.is_stale(latest, now):
        st.warning(f"Data may be out of date: latest interval is {latest:%d %b %Y %H:%M} NEM time.")
    st.divider()
    st.caption(f"Latest data: {latest:%d %b %Y %H:%M} NEM time (AEST, UTC+10)")
    st.caption(copy.ATTRIBUTION)
    st.caption(copy.DISCLAIMER)
