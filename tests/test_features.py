from datetime import date

import numpy as np
import pandas as pd
import pytest

from forecast import benchmarks, features
from forecast.features import LeakageError

D = date(2026, 11, 5)


def series(start="2026-10-01", end="2026-11-07", freq="30min", fn=lambda t: 1000.0):
    idx = pd.date_range(start, end, freq=freq)
    return pd.Series([fn(t) for t in idx], index=idx)


def test_issue_time_and_targets():
    assert features.issue_time_for(D) == pd.Timestamp("2026-11-04 12:00")
    tt = features.target_times(D)
    assert len(tt) == 48
    assert tt[0] == pd.Timestamp("2026-11-05 00:30") and tt[-1] == pd.Timestamp("2026-11-06 00:00")


def test_lags_never_after_issue_time():
    demand = series(fn=lambda t: t.day * 100 + t.hour)
    X = features.build_features(demand, series(freq="1h", fn=lambda t: 20.0), "VIC1",
                                features.target_times(D), features.issue_time_for(D))
    assert list(X.columns) == ["half_hour", "dow", "month", "is_holiday", "temp_c", "temp_c_sq",
                               "lag_2d_mw", "lag_7d_mw"]
    # lag_2d for target 2026-11-05 18:00 is demand at 2026-11-03 18:00 (= 3*100 + 18)
    assert X.loc[pd.Timestamp("2026-11-05 18:00"), "lag_2d_mw"] == 318
    assert X.loc[pd.Timestamp("2026-11-05 18:00"), "lag_7d_mw"] == 2918  # 2026-10-29 18:00


def test_one_day_lag_raises_leakage():
    with pytest.raises(LeakageError):
        features._lag(series(), pd.DatetimeIndex([pd.Timestamp("2026-11-05 18:00")]), 1,
                      features.issue_time_for(D))


def test_holiday_flag_uses_state():
    temps = series(freq="1h", fn=lambda t: 20.0)
    def flag(region, d):
        X = features.build_features(series(), temps, region, features.target_times(d),
                                    features.issue_time_for(d))
        return bool(X["is_holiday"].iloc[10])
    melbourne_cup = date(2026, 11, 3)
    assert flag("VIC1", melbourne_cup) is True
    assert flag("NSW1", melbourne_cup) is False


def test_half_hour_feature_uses_period_start():
    X = features.build_features(series(), series(freq="1h", fn=lambda t: 20.0), "SA1",
                                features.target_times(D), features.issue_time_for(D))
    assert X["half_hour"].tolist() == list(range(48))
    assert X["dow"].nunique() == 1  # the 24:00 period still belongs to the target day


def test_temperature_interpolated_to_half_hours():
    temps = series(freq="1h", fn=lambda t: float(t.hour))
    X = features.build_features(series(), temps, "SA1", features.target_times(D),
                                features.issue_time_for(D))
    assert X.loc[pd.Timestamp("2026-11-05 10:30"), "temp_c"] == pytest.approx(10.5)
    assert X.loc[pd.Timestamp("2026-11-05 10:30"), "temp_c_sq"] == pytest.approx(110.25)


def test_naive_is_seven_days_earlier():
    demand = series(fn=lambda t: float(t.day))
    out = benchmarks.naive_forecast(demand, features.target_times(D))
    assert out.iloc[0] == 29.0  # 2026-10-29 00:30
    assert np.allclose(out.iloc[1:47], 29.0)


def test_aemo_benchmark_picks_latest_run_before_issue():
    tt = features.target_times(D)
    runs = []
    for issue, mw in (("2026-11-04 11:30", 1.0), ("2026-11-04 12:00", 2.0), ("2026-11-04 12:30", 3.0)):
        runs += [{"issue_time": pd.Timestamp(issue), "target_time": t, "aemo_mw": mw} for t in tt]
    out = benchmarks.aemo_benchmark(pd.DataFrame(runs), tt, features.issue_time_for(D))
    assert set(out) == {2.0}
