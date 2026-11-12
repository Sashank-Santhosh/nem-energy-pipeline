"""NEM time: AEST, UTC+10 all year (no daylight saving). Every timestamp in the project uses it."""

from datetime import UTC, datetime

import pandas as pd

NEM_OFFSET = pd.Timedelta(hours=10)


def nem_now(clock=lambda: datetime.now(UTC)) -> pd.Timestamp:
    return pd.Timestamp(clock()).tz_convert("UTC").tz_localize(None) + NEM_OFFSET
