"""Hourly temperatures from Open-Meteo, always in NEM time (Australia/Brisbane, no DST)."""

import json
from datetime import date, datetime
from typing import Literal
from urllib.parse import urlencode

import pandas as pd

from ingest import state
from ingest.http import fetch as default_fetch
from ingest.sources import CITY_COORDS, OPEN_METEO

Kind = Literal["archive", "forecast", "historical_forecast"]


def fetch_temperatures(region: str, start: date, end: date, kind: Kind,
                       fetch=default_fetch) -> pd.DataFrame:
    lat, lon = CITY_COORDS[region]
    q = urlencode({"latitude": lat, "longitude": lon, "hourly": "temperature_2m",
                   "timezone": "Australia/Brisbane",
                   "start_date": start.isoformat(), "end_date": end.isoformat()})
    body = json.loads(fetch(f"{OPEN_METEO[kind]}?{q}"))
    h = body["hourly"]
    return pd.DataFrame({
        "time": pd.to_datetime(h["time"]),
        "region": region,
        "temperature_c": pd.to_numeric(pd.Series(h["temperature_2m"]), errors="coerce"),
        "kind": kind,
        "fetched_at": datetime.now(),
    })


def load_weather(con, df: pd.DataFrame) -> int:
    state.ensure_schema(con)
    return state.append(con, "raw.weather", df)
