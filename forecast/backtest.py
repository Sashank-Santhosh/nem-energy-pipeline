"""Rolling-origin backtest: refit every `refit_days`, never training on the future."""

from datetime import date, timedelta

import pandas as pd

from forecast import model
from forecast.data import Inputs
from forecast.features import FEATURES, issue_time_for

COLUMNS = ["regionid", "issue_time", "target_time", "actual_mw", "model_mw", "naive_mw", "aemo_mw"]


def _days(a: date, b: date) -> list[date]:
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def rolling_backtest(con, region: str, start: date, end: date, refit_days: int = 7) -> pd.DataFrame:
    inp = Inputs(con, region, train_kind="archive", target_kind="historical_forecast")
    first_demand = inp.demand.index.min().date()
    history = {d: inp.day(d, "archive") for d in _days(first_demand + timedelta(days=8), end)}
    out = []
    for block_start in _days(start, end)[::refit_days]:
        issue0 = issue_time_for(block_start)
        train = pd.concat([f for d, f in history.items() if f.index.max() <= issue0])
        train = train.dropna(subset=FEATURES + ["actual_mw"])
        m = model.train(train[FEATURES], train["actual_mw"])
        for d in _days(block_start, min(block_start + timedelta(days=refit_days - 1), end)):
            f = inp.day(d, "historical_forecast")
            f = f.dropna(subset=FEATURES)
            if f.empty:
                continue
            out.append(pd.DataFrame({
                "regionid": region, "issue_time": f["issue_time"], "target_time": f.index,
                "actual_mw": f["actual_mw"], "model_mw": model.predict(m, f[FEATURES]),
                "naive_mw": f["naive_mw"], "aemo_mw": f["aemo_mw"]}))
    return pd.concat(out, ignore_index=True)[COLUMNS] if out else pd.DataFrame(columns=COLUMNS)
