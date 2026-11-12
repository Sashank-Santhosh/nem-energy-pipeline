"""Daily job: at 13:00 NEM time, forecast tomorrow's 48 half-hours for every region."""

import logging
from datetime import timedelta

import pandas as pd

from forecast import model, store
from forecast.backtest import _days
from forecast.data import Inputs
from forecast.features import FEATURES, issue_time_for
from ingest.sources import REGIONS

log = logging.getLogger(__name__)


def forecast_region(con, region: str, now: pd.Timestamp) -> pd.DataFrame | None:
    target = (now + timedelta(days=1)).date()
    issue = issue_time_for(target)
    inp = Inputs(con, region, train_kind="archive", target_kind="forecast")
    if inp.demand.empty:
        log.warning("%s: no demand history, skipped", region)
        return None
    first = inp.demand.index.min().date() + timedelta(days=8)
    history = [inp.day(d, "archive") for d in _days(first, target - timedelta(days=2))]
    train = pd.concat(history).dropna(subset=FEATURES + ["actual_mw"]) if history else None
    f = inp.day(target, "forecast", fetched_before=issue)
    if train is None or train.empty or f[FEATURES].isna().any().any():
        missing = [c for c in FEATURES if f[c].isna().any()]
        log.warning("%s: missing inputs %s for %s, skipped", region, missing or "history", target)
        return None
    m = model.train(train[FEATURES], train["actual_mw"])
    return pd.DataFrame({"regionid": region, "issue_time": issue, "target_time": f.index,
                         "model_mw": model.predict(m, f[FEATURES]).to_numpy(),
                         "naive_mw": f["naive_mw"].to_numpy(), "created_at": pd.Timestamp.now()})


def run_daily(con, now: pd.Timestamp) -> pd.DataFrame:
    store.ensure_tables(con)
    parts = [p for r in REGIONS if (p := forecast_region(con, r, now)) is not None]
    if not parts:
        return pd.DataFrame(columns=["regionid", "issue_time", "target_time", "model_mw",
                                     "naive_mw", "created_at"])
    out = pd.concat(parts, ignore_index=True)
    con.register("_fc", out)
    con.execute("delete from forecasts.daily f using (select distinct regionid, issue_time from _fc)"
                " n where f.regionid = n.regionid and f.issue_time = n.issue_time")
    con.execute("insert into forecasts.daily select regionid, issue_time, target_time, model_mw,"
                " naive_mw, created_at from _fc")
    con.unregister("_fc")
    return out
