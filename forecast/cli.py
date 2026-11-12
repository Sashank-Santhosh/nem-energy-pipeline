"""Command line: `daily` forecast or `backtest`."""

import argparse
import logging
import sys
from datetime import timedelta

import duckdb
import pandas as pd

from forecast import store
from forecast.backtest import rolling_backtest
from forecast.daily import run_daily, run_if_due
from forecast.metrics import mae, mape
from ingest.sources import REGIONS
from ingest.timeutil import nem_now


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="forecast.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("daily")
    d.add_argument("--db", required=True)
    due = sub.add_parser("daily-if-due", help="forecast tomorrow once, after 13:00 NEM time")
    due.add_argument("--db", required=True)
    b = sub.add_parser("backtest")
    b.add_argument("--db", required=True)
    b.add_argument("--months", type=int, default=6)
    a = ap.parse_args(argv)

    with duckdb.connect(a.db) as con:
        store.ensure_tables(con)
        if a.cmd == "daily-if-due":
            print(f"wrote {run_if_due(con, nem_now())} forecast rows")
            return 0
        if a.cmd == "daily":
            out = run_daily(con, nem_now())
            print(f"wrote {len(out)} forecast rows for {sorted(set(out['regionid']))}")
            return 0
        end = (nem_now() - timedelta(days=2)).date()
        start = end - timedelta(days=30 * a.months)
        parts = [rolling_backtest(con, r, start, end) for r in REGIONS]
        bt = pd.concat(parts, ignore_index=True)
        con.execute("delete from forecasts.backtest")
        con.register("_bt", bt)
        con.execute("insert into forecasts.backtest select * from _bt")
        # Open-Meteo historical forecasts are short-lead, so backtest weather is optimistic.
        con.execute("insert into forecasts.backtest_meta values (true, now(), ?)", [a.months])
        for r, g in bt.groupby("regionid"):
            print(r, {k: round(mae(g.actual_mw, g[k]), 1) for k in ("model_mw", "naive_mw", "aemo_mw")},
                  {k: round(mape(g.actual_mw, g[k]), 2) for k in ("model_mw", "naive_mw", "aemo_mw")})
    return 0


if __name__ == "__main__":
    sys.exit(main())
