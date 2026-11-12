"""The two forecasts the model is compared against."""

import pandas as pd


def naive_forecast(demand: pd.Series, targets: pd.DatetimeIndex) -> pd.Series:
    """Same half-hour one week earlier."""
    return pd.Series(demand.reindex(targets - pd.Timedelta(days=7)).to_numpy(), index=targets)


def aemo_benchmark(aemo: pd.DataFrame, targets: pd.DatetimeIndex,
                   issue_time: pd.Timestamp) -> pd.Series:
    """AEMO's pre-dispatch forecast from the latest run issued at or before issue_time."""
    runs = aemo[aemo["issue_time"] <= issue_time]
    if runs.empty:
        return pd.Series(float("nan"), index=targets)
    latest = runs[runs["issue_time"] == runs["issue_time"].max()]
    return latest.set_index("target_time")["aemo_mw"].reindex(targets)
