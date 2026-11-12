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
        # No AEMO run covering TAS1's 2026-11-10: those half-hours must not be scored at all.
        con.execute("delete from raw.predispatch_regionsum where regionid = 'TAS1' "
                    "and predispatchseqno like '20261109%'")
    run_dbt(path)
    with duckdb.connect(str(path)) as con:
        for day in ("2026-11-07", "2026-11-08", "2026-11-09"):
            daily.run_daily(con, pd.Timestamp(day) + pd.Timedelta(hours=13, minutes=5))
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


def test_missing_values_show_as_not_available():
    from dashboard.ui import fmt

    assert fmt(None, "{:,.0f} MW") == "n/a"
    assert fmt(float("nan"), "{:.0%}") == "n/a"
    assert fmt(0.0, "{:,.0f} MW") == "0 MW"
    assert fmt(1234.4, "{:,.0f} MW") == "1,234 MW"


def test_accuracy_scores_all_sources_on_the_same_rows(con):
    rows = con.execute("""select regionid, period, count(*) n,
            count(*) filter (where model_mw is not null and naive_mw is not null
                             and aemo_mw is not null and actual_mw is not null) complete
        from marts.fct_forecast_accuracy group by 1, 2""").fetchall()
    assert rows and all(n == complete for _, _, n, complete in rows)


def test_hourly_refresh_reuses_disk_and_closes_old_connection(db, tmp_path, monkeypatch):
    payload = Path(db).read_bytes()

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def raise_for_status(self):
            pass

        def iter_content(self, n):
            yield payload

    monkeypatch.delenv("NEM_DB_PATH", raising=False)
    monkeypatch.setenv("NEM_DB_URL", "https://example.invalid/nem.duckdb")
    monkeypatch.setattr(data.requests, "get", lambda *a, **k: Resp())
    monkeypatch.setattr(data, "DOWNLOAD_DIR", tmp_path)
    first = data.get_connection()
    second = data.get_connection()
    with pytest.raises(duckdb.Error):
        first.execute("select 1")  # closed
    assert second.execute("select count(*) from marts.fct_region_interval").fetchone()[0] > 0
    assert len(list(tmp_path.glob("*.duckdb"))) == 1
    second.close()


def test_download_falls_back_to_previous_copy(tmp_path, monkeypatch):
    asked = []

    class Resp:
        def __init__(self, url):
            self.url = url

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def raise_for_status(self):
            if self.url.endswith("/nem.duckdb"):
                raise data.requests.HTTPError("404 during an upload swap")

        def iter_content(self, n):
            yield b"x"

    def get(url, **_):
        asked.append(url)
        return Resp(url)

    monkeypatch.setattr(data.requests, "get", get)
    monkeypatch.setattr(data, "DOWNLOAD_DIR", tmp_path)
    data._download("https://h/releases/download/data-latest/nem.duckdb")
    assert asked[-1] == "https://h/releases/download/data-latest/nem-prev.duckdb"
