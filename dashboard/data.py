"""Read-only queries behind the dashboard. Every function takes an open DuckDB connection."""

import os
import tempfile
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import requests

FUELS = ["solar", "wind", "coal", "gas", "hydro", "battery", "other"]
ACCURACY_COLS = ["regionid", "source", "period", "mae_mw", "mape_pct"]


DOWNLOAD_DIR = Path(tempfile.gettempdir())
_current: dict = {}  # the downloaded copy in use: {"path": Path, "con": connection}


def _download(url: str) -> Path:
    """Download to a fresh file, then switch to it; the previous copy is closed and deleted,
    so hourly refreshes never pile up copies on disk."""
    new = DOWNLOAD_DIR / f"nem-dashboard-{os.getpid()}-{os.urandom(4).hex()}.duckdb"
    # The release keeps the previous upload as nem-prev.duckdb; use it if the current copy is
    # mid-swap or missing.
    for candidate in (url, url.replace("/nem.duckdb", "/nem-prev.duckdb")):
        try:
            with new.open("wb") as f, requests.get(candidate, stream=True, timeout=120) as r:
                r.raise_for_status()
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
            return new
        except requests.RequestException:
            if candidate != url:
                raise
    return new


def get_connection(path: str | None = None) -> duckdb.DuckDBPyConnection:
    """Open the database read-only: an explicit path, NEM_DB_PATH, or a download of NEM_DB_URL."""
    path = path or os.environ.get("NEM_DB_PATH")
    if path:
        return duckdb.connect(path, read_only=True)
    new = _download(os.environ["NEM_DB_URL"])
    con = duckdb.connect(str(new), read_only=True)
    old = _current.copy()
    _current.update(path=new, con=con)
    if old:
        old["con"].close()
        Path(old["path"]).unlink(missing_ok=True)
    return con


def _has(con, table: str) -> bool:
    schema, name = table.split(".")
    return con.execute("select count(*) from information_schema.tables where table_schema = ? "
                       "and table_name = ?", [schema, name]).fetchone()[0] > 0


def latest_interval(con) -> pd.Timestamp:
    return pd.Timestamp(con.execute("select max(interval_end) from marts.fct_region_interval")
                        .fetchone()[0])


def is_stale(latest: pd.Timestamp, now: pd.Timestamp, max_age_hours: int = 3) -> bool:
    return (now - latest) > pd.Timedelta(hours=max_age_hours)


def headline_cards(con, region: str) -> dict:
    row = con.execute("""
        with d as (select * from marts.fct_region_daily where regionid = $r),
             latest as (select max(trading_date) t from d)
        select (select min_demand_mw from d, latest where trading_date = latest.t - 1),
               (select min_demand_mw from d, latest where trading_date = latest.t - 365),
               (select sum(negative_price_intervals) from d, latest
                 where date_trunc('month', trading_date) = date_trunc('month', latest.t)),
               (select avg((coalesce(solar_mw, 0) + coalesce(rooftop_pv_mw, 0))
                           / nullif(demand_mw + coalesce(rooftop_pv_mw, 0), 0))
                  from marts.fct_region_interval, latest
                 where regionid = $r and hour(interval_end - interval 5 minute) between 11 and 13
                   and interval_end >= latest.t - interval 7 day)
        """, {"r": region}).fetchone()
    keys = ["min_demand_today", "min_demand_year_ago", "negative_intervals_month",
            "midday_solar_share"]
    return dict(zip(keys, row, strict=True))


def duck_curve(con, region: str, month: date) -> pd.DataFrame:
    return con.execute("""
        with slots as (
            select strftime(timestamp '2000-01-01' + i * interval 5 minute, '%H:%M') as time_of_day
            from range(1, 289) t(i)),
        x as (
            select strftime(interval_end, '%H:%M') as time_of_day,
                   date_trunc('month', interval_end - interval 5 minute) as m, demand_mw
            from marts.fct_region_interval where regionid = $r)
        select s.time_of_day,
               avg(x.demand_mw) filter (where x.m = $m) as this_year_mw,
               avg(x.demand_mw) filter (where x.m = $m - interval 1 year) as last_year_mw
        from slots s left join x using (time_of_day)
        group by 1 order by (s.time_of_day = '00:00'), 1
        """, {"r": region, "m": pd.Timestamp(month).replace(day=1)}).df()


def negative_price_counts(con) -> pd.DataFrame:
    return con.execute("""
        select date_trunc('month', trading_date) as month, regionid,
               sum(negative_price_intervals) as intervals
        from marts.fct_region_daily group by 1, 2 having intervals > 0 order by 1, 2
        """).df()


def fuel_mix_by_hour(con, region: str) -> pd.DataFrame:
    cols = ", ".join(f"{f}_mw as {f}" for f in FUELS)
    return con.execute(f"""
        with x as (
            select hour(interval_end - interval 5 minute) as hour, {cols},
                   rooftop_pv_mw as "rooftop solar"
            from marts.fct_region_interval
            where regionid = $r and interval_end >= (select max(interval_end)
                                                     from marts.fct_region_interval) - interval 30 day)
        unpivot x on {", ".join(FUELS)}, "rooftop solar" into name fuel value mw
        """, {"r": region}).df().groupby(["hour", "fuel"], as_index=False)["mw"].mean()


def forecast_vs_aemo(con, region: str, target_date: date) -> pd.DataFrame:
    cols = ["target_time", "model_mw", "aemo_mw", "actual_mw"]
    if not _has(con, "forecasts.daily"):
        return pd.DataFrame(columns=cols)
    return con.execute("""
        with f as (
            select * from forecasts.daily
            where regionid = $r and cast(target_time - interval 30 minute as date) = $d
            qualify issue_time = max(issue_time) over ()),
        a as (
            select f.target_time, a.aemo_mw from f join marts.fct_aemo_forecast a
              on a.regionid = f.regionid and a.target_time = f.target_time
             and a.issue_time <= f.issue_time
            qualify row_number() over (partition by f.target_time order by a.issue_time desc) = 1)
        select f.target_time, f.model_mw, a.aemo_mw, h.demand_mw as actual_mw
        from f left join a using (target_time)
        left join marts.fct_demand_half_hourly h
          on h.regionid = f.regionid and h.period_end = f.target_time
        order by 1
        """, {"r": region, "d": target_date}).df()[cols]


def accuracy_table(con) -> pd.DataFrame:
    if not _has(con, "marts.fct_forecast_accuracy"):
        return pd.DataFrame(columns=ACCURACY_COLS)
    return con.execute("""
        with x as (
            select regionid, actual_mw, model_mw, naive_mw, aemo_mw,
                   case when period = 'backtest' then 'backtest' else 'live_30d' end as period
            from marts.fct_forecast_accuracy
            where period = 'backtest'
               or target_time >= (select max(target_time) from marts.fct_forecast_accuracy
                                  where period = 'live') - interval 30 day),
        u as (unpivot x on model_mw, naive_mw, aemo_mw into name source value pred)
        select regionid, replace(source, '_mw', '') as source, period,
               avg(abs(pred - actual_mw)) as mae_mw,
               100 * avg(abs(pred - actual_mw) / abs(actual_mw))
                   filter (where abs(actual_mw) >= 1) as mape_pct
        from u group by 1, 2, 3 order by 1, 3, 2
        """).df()[ACCURACY_COLS]
