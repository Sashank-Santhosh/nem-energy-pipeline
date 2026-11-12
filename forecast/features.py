"""Leak-safe features for a day-ahead, half-hourly demand forecast issued at 13:00 NEM time.

13:00 because AEMO's first pre-dispatch run covering all of tomorrow is issued at 12:30.
"""

from datetime import date, timedelta

import holidays
import numpy as np
import pandas as pd

from ingest.sources import HOLIDAY_SUBDIV

HALF_HOUR = pd.Timedelta(minutes=30)
ISSUE_HOUR = 13
FEATURES = ["half_hour", "dow", "month", "is_holiday", "temp_c", "temp_c_sq",
            "lag_2d_mw", "lag_7d_mw"]


class LeakageError(ValueError):
    """A feature tried to use information from after the forecast's issue time."""


def issue_time_for(target_date: date) -> pd.Timestamp:
    return pd.Timestamp(target_date - timedelta(days=1)) + pd.Timedelta(hours=ISSUE_HOUR)


def target_times(target_date: date) -> pd.DatetimeIndex:
    return pd.date_range(pd.Timestamp(target_date) + HALF_HOUR, periods=48, freq="30min")


def _lag(demand: pd.Series, targets: pd.DatetimeIndex, days: int,
         issue_time: pd.Timestamp) -> np.ndarray:
    looked_up = targets - pd.Timedelta(days=days)
    if (looked_up > issue_time).any():
        raise LeakageError(f"{days}-day lag reaches {looked_up.max()} after issue {issue_time}")
    return demand.reindex(looked_up).to_numpy(dtype=float)


def _temps_at(temps: pd.Series, targets: pd.DatetimeIndex) -> np.ndarray:
    idx = temps.index.union(targets)
    return temps.reindex(idx).interpolate(method="time").reindex(targets).to_numpy(dtype=float)


def build_features(demand: pd.Series, temps: pd.Series, region: str,
                   targets: pd.DatetimeIndex, issue_time: pd.Timestamp) -> pd.DataFrame:
    start = targets - HALF_HOUR  # calendar features use the period's start (24:00 -> same day)
    hol = holidays.country_holidays("AU", subdiv=HOLIDAY_SUBDIV[region],
                                    years=sorted(set(start.year)))
    temp = _temps_at(temps, targets)
    return pd.DataFrame({
        "half_hour": start.hour * 2 + start.minute // 30,
        "dow": start.day_of_week,
        "month": start.month,
        "is_holiday": [d in hol for d in start.date],
        "temp_c": temp,
        "temp_c_sq": temp ** 2,
        "lag_2d_mw": _lag(demand, targets, 2, issue_time),
        "lag_7d_mw": _lag(demand, targets, 7, issue_time),
    }, index=targets)
