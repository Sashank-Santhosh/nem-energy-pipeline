"""Read model inputs from the marts (and staging weather)."""

from datetime import date

import pandas as pd

from forecast.benchmarks import aemo_benchmark, naive_forecast
from forecast.features import build_features, issue_time_for, target_times


class Inputs:
    """Demand, temperatures and AEMO runs for one region, read once."""

    def __init__(self, con, region: str, train_kind: str, target_kind: str):
        self.region = region
        self.demand = con.execute(
            "select period_end, demand_mw from marts.fct_demand_half_hourly where regionid = ? "
            "order by 1", [region]).df().set_index("period_end")["demand_mw"]
        self.weather = con.execute(
            "select time, temperature_c, kind, fetched_at from staging.stg_weather "
            "where regionid = ?", [region]).df()
        self.aemo = con.execute(
            "select issue_time, target_time, aemo_mw from marts.fct_aemo_forecast "
            "where regionid = ?", [region]).df()
        self.train_kind, self.target_kind = train_kind, target_kind

    def temps(self, kind: str, fetched_before: pd.Timestamp | None = None) -> pd.Series:
        w = self.weather[self.weather["kind"] == kind]
        if fetched_before is not None:
            w = w[w["fetched_at"] <= fetched_before]
        w = w.sort_values("fetched_at").drop_duplicates("time", keep="last")
        return w.set_index("time")["temperature_c"].sort_index()

    def day(self, d: date, kind: str, fetched_before: pd.Timestamp | None = None) -> pd.DataFrame:
        """Features, actuals and both benchmarks for one target day."""
        tt, issue = target_times(d), issue_time_for(d)
        X = build_features(self.demand, self.temps(kind, fetched_before), self.region, tt, issue)
        X["actual_mw"] = self.demand.reindex(tt).to_numpy()
        X["naive_mw"] = naive_forecast(self.demand, tt).to_numpy()
        X["aemo_mw"] = aemo_benchmark(self.aemo, tt, issue).to_numpy()
        X["issue_time"] = issue
        return X
