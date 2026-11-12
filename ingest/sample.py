"""Build a small, deterministic sample database: real fixtures through the real loaders,
plus 14 days of synthetic rows in the same raw format (for dbt, forecast and dashboard tests)."""

from datetime import date, datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from ingest import nemweb, openmeteo, state
from ingest.fuel_map import load_fuel_map
from ingest.sources import FOLDERS, NEMWEB_BASE, REGIONS

FIX = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
END = pd.Timestamp("2026-11-11 00:00")
DAYS = 14
BASE_MW = {"NSW1": 7500, "QLD1": 6500, "VIC1": 5000, "SA1": 1400, "TAS1": 1100}
LOADED_AT = datetime(2026, 11, 11, 1, 0)


def _fmt(ts: pd.Series) -> pd.Series:
    return ts.dt.strftime("%Y/%m/%d %H:%M:%S")


def synthetic_demand(ts: pd.Series, region: str) -> np.ndarray:
    h = ts.dt.hour + ts.dt.minute / 60
    evening = np.exp(-((h - 18.5) ** 2) / 4)
    midday_dip = np.exp(-((h - 12.5) ** 2) / 6)
    return np.asarray(BASE_MW[region] * (1 + 0.25 * evening - 0.3 * midday_dip))


def _range(freq: str, extra_days: int = 0) -> pd.Series:
    start = END - pd.Timedelta(days=DAYS)
    return pd.Series(pd.date_range(start, END + pd.Timedelta(days=extra_days), freq=freq,
                                   inclusive="right"))


def _predispatch_rows(region: str) -> pd.DataFrame:
    rows = []
    for day in pd.date_range(END - pd.Timedelta(days=DAYS), END, freq="D", inclusive="left"):
        for period in ("18", "19"):
            issue = day + pd.Timedelta(hours=4) + pd.Timedelta(minutes=30 * (int(period) - 1))
            targets = pd.Series(pd.date_range(issue + pd.Timedelta(minutes=30), periods=72,
                                              freq="30min"))
            for t, mw in zip(targets, synthetic_demand(targets, region) * 1.01, strict=True):
                rows.append({"predispatchseqno": day.strftime("%Y%m%d") + period, "runno": "1",
                             "regionid": region, "periodid": "", "intervention": "0",
                             "totaldemand": f"{mw:.2f}", "datetime": t.strftime("%Y/%m/%d %H:%M:%S")})
    return pd.DataFrame(rows).assign(source_file="synthetic", loaded_at=LOADED_AT)


def _synthetic(con, rng) -> None:
    t5, t30, th = _range("5min"), _range("30min"), _range("1h", extra_days=2)
    for r in REGIONS:
        d = synthetic_demand(t5, r) + rng.normal(0, 20, len(t5))
        price = np.where(t5.dt.hour.between(11, 14), -20.0, 90.0) + rng.normal(0, 5, len(t5))
        common = {"settlementdate": _fmt(t5), "runno": "1", "regionid": r, "intervention": "0",
                  "source_file": "synthetic", "loaded_at": LOADED_AT}
        state.append(con, "raw.dispatch_regionsum",
                     pd.DataFrame({**common, "totaldemand": [f"{x:.2f}" for x in d]}))
        state.append(con, "raw.dispatch_price",
                     pd.DataFrame({**common, "rrp": [f"{x:.2f}" for x in price]}))
        pv = np.clip(np.sin((t30.dt.hour + t30.dt.minute / 60 - 6) / 12 * np.pi), 0, None)
        state.append(con, "raw.rooftop_pv_actual", pd.DataFrame({
            "interval_datetime": _fmt(t30), "regionid": r,
            "power": [f"{x:.3f}" for x in 0.3 * BASE_MW[r] * pv], "qi": "1",
            "type": "MEASUREMENT", "source_file": "synthetic", "loaded_at": LOADED_AT}))
        for fuel, share in (("coal", 0.5), ("gas", 0.1), ("wind", 0.2), ("solar", 0.15),
                            ("hydro", 0.05)):
            state.append(con, "raw.fuel_mix", pd.DataFrame({
                "settlementdate": _fmt(t5), "regionid": r, "fuel": fuel, "mw": d * share,
                "source_file": "synthetic", "loaded_at": LOADED_AT}))
        temps = 20 + 6 * np.sin((th.dt.hour - 9) / 24 * 2 * np.pi)
        for kind in ("archive", "forecast", "historical_forecast"):
            state.append(con, "raw.weather", pd.DataFrame({
                "time": th, "region": r, "temperature_c": temps + rng.normal(0, 0.5, len(th)),
                "kind": kind, "fetched_at": th - pd.Timedelta(hours=40)}))
        state.append(con, "raw.predispatch_regionsum", _predispatch_rows(r))


def _load_fixtures(con) -> None:
    nem = FIX / "nemweb"
    files = {"dispatch": "dispatchis.zip", "rooftop_pv": "rooftop_measurement.zip",
             "scada": "dispatchscada.zip", "predispatch": "predispatchis.zip"}
    fmap = load_fuel_map((FIX / "registration_sample.xlsx").read_bytes())
    for source, name in files.items():
        folder = NEMWEB_BASE + FOLDERS[source]
        pages = {folder: f'<a href="{FOLDERS[source]}{name}">x</a>'.encode(),
                 folder + name: (nem / name).read_bytes()}
        kw = {"fuel_map": fmap} if source == "scada" else {}
        nemweb.load_new_files(con, source, folder, fetch=lambda u, p=pages, **_: p[u], **kw)
    om = (FIX / "openmeteo" / "archive_adelaide.json").read_bytes()
    openmeteo.load_weather(con, openmeteo.fetch_temperatures(
        "SA1", date(2026, 10, 3), date(2026, 10, 5), "archive", fetch=lambda u, **_: om))


def build_sample(out: Path) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    con = duckdb.connect(str(out))
    state.ensure_schema(con)
    _load_fixtures(con)
    _synthetic(con, np.random.default_rng(42))
    con.close()
    return out
