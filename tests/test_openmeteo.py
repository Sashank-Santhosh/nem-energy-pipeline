from datetime import date

from ingest import openmeteo
from tests.conftest import FIX


class Capture:
    def __init__(self, body):
        self.body, self.urls = body, []

    def __call__(self, url, **_):
        self.urls.append(url)
        return self.body


ARCHIVE = (FIX / "openmeteo" / "archive_adelaide.json").read_bytes()


def test_request_uses_brisbane_timezone():
    cap = Capture(ARCHIVE)
    openmeteo.fetch_temperatures("SA1", date(2026, 10, 3), date(2026, 10, 5), "archive", fetch=cap)
    assert "timezone=Australia%2FBrisbane" in cap.urls[0]
    assert "archive-api.open-meteo.com" in cap.urls[0]


def test_temperatures_align_to_nem_time():
    # 2026-10-04 is the DST start in Adelaide; NEM time must not skip or repeat an hour.
    df = openmeteo.fetch_temperatures("SA1", date(2026, 10, 3), date(2026, 10, 5), "archive",
                                      fetch=Capture(ARCHIVE))
    assert len(df) == 72
    assert df["time"].is_unique
    assert str(df["time"].iloc[0]) == "2026-10-03 00:00:00"
    assert (df["time"].diff().dropna().dt.total_seconds() == 3600).all()
    assert set(df["region"]) == {"SA1"} and set(df["kind"]) == {"archive"}


def test_load_weather_appends(con):
    df = openmeteo.fetch_temperatures("SA1", date(2026, 10, 3), date(2026, 10, 5), "archive",
                                      fetch=Capture(ARCHIVE))
    openmeteo.load_weather(con, df)
    openmeteo.load_weather(con, df)
    assert con.execute("select count(*) from raw.weather").fetchone()[0] == 144
