from datetime import date

import duckdb
import numpy as np
import pandas as pd
import pytest

from forecast import backtest, model
from forecast.metrics import mae


def make_db(days=60, seed=0, end="2026-11-01"):
    """Marts-shaped tables with demand driven by time of day and temperature."""
    rng = np.random.default_rng(seed)
    t = pd.date_range(pd.Timestamp(end) - pd.Timedelta(days=days), end, freq="30min")[1:]
    th = pd.date_range(t[0].floor("D"), pd.Timestamp(end) + pd.Timedelta(days=2), freq="1h")
    temp_h = pd.Series(20 + 8 * np.sin(np.arange(len(th)) / 37.0), index=th)
    temp = temp_h.reindex(temp_h.index.union(t)).interpolate("time").reindex(t)
    hour = t.hour + t.minute / 60
    demand = 1000 + 300 * np.sin(2 * np.pi * hour / 24) + 20 * temp.to_numpy() \
        + rng.normal(0, 10, len(t))
    con = duckdb.connect(":memory:")
    for s in ("marts", "staging"):
        con.execute(f"create schema {s}")
    d = pd.DataFrame({"regionid": "SA1", "period_end": t, "demand_mw": demand})
    w = pd.concat([pd.DataFrame({"regionid": "SA1", "time": th, "temperature_c": temp_h.values,
                                 "kind": k, "fetched_at": th - pd.Timedelta(hours=40)})
                   for k in ("archive", "forecast", "historical_forecast")])
    a = pd.DataFrame({"regionid": "SA1", "issue_time": pd.Timestamp("2026-01-01"),
                      "target_time": t, "aemo_mw": demand * 1.02})
    for name, df in (("d", d), ("w", w), ("a", a)):
        con.register(name, df)
    con.execute("create table marts.fct_demand_half_hourly as select * from d")
    con.execute("create table staging.stg_weather as select * from w")
    con.execute("create table marts.fct_aemo_forecast as select * from a")
    return con


def test_backtest_never_trains_on_future(monkeypatch):
    seen = []
    real = model.train

    def spy(X, y):
        seen.append(X.index.max())
        return real(X, y)

    monkeypatch.setattr(model, "train", spy)
    out = backtest.rolling_backtest(make_db(), "SA1", date(2026, 10, 15), date(2026, 10, 28))
    blocks = sorted(out["issue_time"].unique())
    assert len(seen) == 2  # 14 days, refit every 7
    for trained_until, first_issue in zip(seen, blocks[::7], strict=True):
        assert trained_until <= first_issue


def test_backtest_output_shape():
    out = backtest.rolling_backtest(make_db(), "SA1", date(2026, 10, 20), date(2026, 10, 21))
    assert list(out.columns) == ["regionid", "issue_time", "target_time", "actual_mw", "model_mw",
                                 "naive_mw", "aemo_mw"]
    assert len(out) == 96
    assert out["aemo_mw"].notna().all()


def test_model_beats_naive_on_synthetic():
    out = backtest.rolling_backtest(make_db(days=90), "SA1", date(2026, 10, 15), date(2026, 10, 28))
    assert mae(out.actual_mw, out.model_mw) < mae(out.actual_mw, out.naive_mw)


def test_train_is_deterministic():
    X = pd.DataFrame({"a": np.arange(200.0), "b": np.arange(200.0) % 7})
    y = pd.Series(X.a * 2 + X.b)
    p1 = model.predict(model.train(X, y), X)
    p2 = model.predict(model.train(X, y), X)
    assert p1.tolist() == pytest.approx(p2.tolist())
