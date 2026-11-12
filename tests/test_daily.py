
import duckdb
import pandas as pd
import pytest

from forecast import daily, store
from ingest.sample import build_sample
from tests.test_dbt_models import run_dbt

NOW = pd.Timestamp("2026-11-09 12:05")  # forecasts 2026-11-10


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "nem.duckdb"
    build_sample(path)
    run_dbt(path)
    return path


def test_daily_writes_48_rows_per_region(db):
    with duckdb.connect(str(db)) as con:
        out = daily.run_daily(con, NOW)
        n = con.execute("select regionid, count(*) from forecasts.daily group by 1").fetchall()
    assert len(out) == 240
    assert sorted(n) == [(r, 48) for r in ("NSW1", "QLD1", "SA1", "TAS1", "VIC1")]
    assert out["issue_time"].unique().tolist() == [pd.Timestamp("2026-11-09 12:00")]


def test_daily_is_idempotent(db):
    with duckdb.connect(str(db)) as con:
        daily.run_daily(con, NOW)
        daily.run_daily(con, NOW)
        assert con.execute("select count(*) from forecasts.daily").fetchone()[0] == 240


def test_daily_skips_region_with_missing_temps(db, caplog):
    with duckdb.connect(str(db)) as con:
        con.execute("delete from raw.weather where region = 'TAS1' and kind = 'forecast'")
    run_dbt(db)
    with duckdb.connect(str(db)) as con:
        out = daily.run_daily(con, NOW)
    assert "TAS1" not in set(out["regionid"])
    assert len(out) == 192
    assert "TAS1" in caplog.text


def test_daily_uses_only_forecasts_fetched_before_issue(db):
    with duckdb.connect(str(db)) as con:
        # A "too new" forecast for every hour of the target day must be ignored.
        con.execute("insert into raw.weather select time, region, 99.0, kind, "
                    "timestamp '2026-11-09 13:00' from raw.weather where kind = 'forecast' "
                    "and cast(time as date) = date '2026-11-10'")
    run_dbt(db)
    with duckdb.connect(str(db)) as con:
        a = daily.run_daily(con, NOW)
    assert a["model_mw"].between(0, 20000).all()
    with duckdb.connect(str(db)) as con:
        temps = con.execute("select max(temperature_c) from staging.stg_weather where kind = "
                            "'forecast' and fetched_at <= timestamp '2026-11-09 12:00'").fetchone()
    assert temps[0] < 99


def test_score_excludes_incomplete_days(db):
    with duckdb.connect(str(db)) as con:
        daily.run_daily(con, pd.Timestamp("2026-11-08 12:05"))  # target 11-09: complete
        daily.run_daily(con, NOW)                                # target 11-10: made incomplete
        con.execute("delete from raw.dispatch_regionsum where regionid = 'SA1' and "
                    "settlementdate = '2026/11/10 15:05:00'")
        store.ensure_tables(con)
    run_dbt(db, "--vars", "{forecasts_ready: true}")
    with duckdb.connect(str(db)) as con:
        days = con.execute("select regionid, cast(target_time - interval 30 minute as date) d, "
                           "count(*) from marts.fct_forecast_accuracy group by 1, 2").fetchall()
    assert ("SA1", pd.Timestamp("2026-11-10").date(), 47) not in days
    assert all(n == 48 for _, _, n in days)
    assert ("SA1", pd.Timestamp("2026-11-09").date(), 48) in days
    assert not any(r == "SA1" and str(d) == "2026-11-10" for r, d, _ in days)
