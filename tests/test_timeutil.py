from datetime import UTC, datetime

import pandas as pd

from ingest.timeutil import nem_now


def test_nem_now_is_utc_plus_10_without_dst():
    utc = datetime(2026, 1, 15, 3, 5, tzinfo=UTC)  # January: Sydney is on DST, NEM is not
    assert nem_now(lambda: utc) == pd.Timestamp("2026-01-15 13:05")
