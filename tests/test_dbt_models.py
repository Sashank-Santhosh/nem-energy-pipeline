import os
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from ingest import state
from ingest.sample import build_sample

ROOT = Path(__file__).resolve().parent.parent
DBT = ROOT / "dbt"


def run_dbt(db: Path, *extra: str) -> None:
    from dbt.cli.main import dbtRunner

    os.environ["NEM_DB"] = str(db)
    res = dbtRunner().invoke(["build", "--project-dir", str(DBT), "--profiles-dir", str(DBT),
                              "--quiet", *extra])
    assert res.success, res.exception


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("dbt") / "nem.duckdb"
    build_sample(path)
    con = duckdb.connect(str(path))
    # The same interval published twice (re-publish / archive overlap), later copy wins.
    dup = con.execute("select * exclude (source_file, loaded_at) from raw.dispatch_regionsum "
                      "where source_file = 'synthetic' limit 5").df()
    state.append(con, "raw.dispatch_regionsum",
                 dup.assign(totaldemand="1234.00", source_file="republished",
                            loaded_at=datetime(2026, 11, 12)))
    # Extreme but real values: market floor price and tiny SA demand.
    t = "2026/11/09 12:00:00"
    con.execute("update raw.dispatch_price set rrp = '-1000.00' "
                "where settlementdate = ? and regionid = 'SA1'", [t])
    con.execute("update raw.dispatch_regionsum set totaldemand = '5.00' "
                "where settlementdate = ? and regionid = 'SA1'", [t])
    con.close()
    run_dbt(path)
    return path


def q(db, sql):
    with duckdb.connect(str(db)) as con:  # dbt holds a read-write handle in-process
        return con.execute(sql).df()


def test_staging_dedupes_repeated_interval(db):
    marts = q(db, "select count(*) n, count(distinct regionid || interval_end) k "
                  "from marts.fct_region_interval")
    assert marts.n[0] == marts.k[0]
    first = q(db, "select * exclude (source_file, loaded_at) from raw.dispatch_regionsum "
                  "where source_file = 'republished' limit 1")
    ts = pd.to_datetime(first.settlementdate[0], format="%Y/%m/%d %H:%M:%S")
    got = q(db, f"select demand_mw from marts.fct_region_interval where regionid = "
                f"'{first.regionid[0]}' and interval_end = '{ts}'")
    assert got.demand_mw.tolist() == [1234.0]


def test_extreme_values_kept(db):
    row = q(db, "select price_rrp, demand_mw, is_negative_price from marts.fct_region_interval "
                "where regionid = 'SA1' and interval_end = '2026-11-09 12:00:00'")
    assert row.to_dict("records") == [{"price_rrp": -1000.0, "demand_mw": 5.0,
                                       "is_negative_price": True}]


def test_daily_negative_price_count(db):
    # Synthetic prices are negative from 11:00 to 14:55 (48 five-minute intervals).
    row = q(db, "select negative_price_intervals from marts.fct_region_daily "
                "where regionid = 'VIC1' and trading_date = '2026-11-05'")
    assert row.negative_price_intervals.tolist() == [48]


def test_half_hourly_only_complete_periods(db):
    df = q(db, "select regionid, count(*) n from marts.fct_demand_half_hourly "
               "where cast(period_end - interval 30 minute as date) = '2026-11-05' group by 1")
    assert set(df.n) == {48}


def test_aemo_forecast_issue_times(db):
    df = q(db, "select distinct strftime(issue_time, '%H:%M') t from marts.fct_aemo_forecast "
               "where regionid = 'NSW1' and target_time < '2026-11-11'")
    assert set(df.t) == {"12:30", "13:00"}


def test_rooftop_prefers_measurement(db):
    with duckdb.connect(str(db)) as con:
        sat = con.execute("select * exclude (source_file, loaded_at) from raw.rooftop_pv_actual "
                          "where source_file = 'synthetic' limit 1").df()
        state.append(con, "raw.rooftop_pv_actual",
                     sat.assign(type="SATELLITE", power="99999", source_file="sat",
                                loaded_at=datetime(2026, 11, 13)))
    run_dbt(db, "--select", "stg_rooftop_pv")
    df = q(db, "select max(rooftop_pv_mw) m from staging.stg_rooftop_pv")
    assert df.m[0] < 99999
