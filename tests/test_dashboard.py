from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from dashboard import copy, data

ROOT = Path(__file__).resolve().parent.parent
import os
import shutil
import subprocess
import sys

from forecast import daily, store
from ingest.sample import build_sample


def run_dbt(db, *extra):
    """dbt in its own process, as in production, so no handle stays open here."""
    env = {**os.environ, "NEM_DB": str(db)}
    dbt = shutil.which("dbt", path=str(Path(sys.executable).parent))
    subprocess.run([dbt, "build", "--project-dir",
                    str(ROOT / "dbt"), "--profiles-dir", str(ROOT / "dbt"), "--quiet",
                    *extra], env=env, check=True)

PAGES = ["dashboard/app.py", "dashboard/pages/1_Solar_and_the_grid.py",
         "dashboard/pages/2_Forecast_accuracy.py"]


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("dash") / "nem.duckdb"
    build_sample(path)
    run_dbt(path)
    with duckdb.connect(str(path)) as con:
        for day in ("2026-11-07", "2026-11-08", "2026-11-09"):
            daily.run_daily(con, pd.Timestamp(day) + pd.Timedelta(hours=12, minutes=5))
        store.ensure_tables(con)
        con.execute("insert into forecasts.backtest select regionid, issue_time, target_time, "
                    "null, model_mw, naive_mw, null from forecasts.daily")
    run_dbt(path, "--vars", "{forecasts_ready: true}")
    return path


@pytest.fixture
def con(db):
    c = data.get_connection(str(db))
    yield c
    c.close()


def test_is_stale_boundaries():
    latest = pd.Timestamp("2026-11-12 09:00")
    assert data.is_stale(latest, latest + pd.Timedelta(hours=2, minutes=59)) is False
    assert data.is_stale(latest, latest + pd.Timedelta(hours=3, minutes=1)) is True


def test_connection_is_read_only(con):
    with pytest.raises(duckdb.Error):
        con.execute("create table x (a int)")


def test_latest_interval(con):
    assert data.latest_interval(con) == pd.Timestamp("2026-11-12 16:35")


def test_duck_curve_has_288_points(con):
    df = data.duck_curve(con, "SA1", date(2026, 11, 1))
    assert list(df.columns) == ["time_of_day", "this_year_mw", "last_year_mw"]
    assert len(df) == 288


def test_headline_cards_keys(con):
    cards = data.headline_cards(con, "SA1")
    assert set(cards) == {"min_demand_today", "min_demand_year_ago", "negative_intervals_month",
                          "midday_solar_share"}
    assert cards["negative_intervals_month"] > 0


def test_negative_price_counts(con):
    df = data.negative_price_counts(con)
    assert list(df.columns) == ["month", "regionid", "intervals"]
    assert (df["intervals"] > 0).all()


def test_fuel_mix_by_hour(con):
    df = data.fuel_mix_by_hour(con, "VIC1")
    assert list(df.columns) == ["hour", "fuel", "mw"]
    assert set(df["hour"]) == set(range(24))


def test_forecast_vs_aemo(con):
    df = data.forecast_vs_aemo(con, "NSW1", date(2026, 11, 10))
    assert list(df.columns) == ["target_time", "model_mw", "aemo_mw", "actual_mw"]
    assert len(df) == 48 and df["model_mw"].notna().all()


def test_accuracy_table_columns(con):
    df = data.accuracy_table(con)
    assert list(df.columns) == ["regionid", "source", "period", "mae_mw", "mape_pct"]
    assert {"model", "naive", "aemo"} <= set(df["source"])
    assert {"backtest", "live_30d"} <= set(df["period"])


@pytest.mark.parametrize("page", PAGES)
def test_pages_render_without_error(db, page, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("NEM_DB_PATH", str(db))
    at = AppTest.from_file(str(ROOT / page), default_timeout=60).run()
    assert not at.exception, at.exception
    text = " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)
    assert copy.ATTRIBUTION in text and copy.DISCLAIMER in text
