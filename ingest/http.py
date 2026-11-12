"""Polite HTTP fetch: sequential, identified, with exponential backoff."""

import time

import requests

from ingest.sources import USER_AGENT


class FetchError(RuntimeError):
    pass


def fetch(url: str, attempts: int = 3, backoff: float = 2.0, sleep=time.sleep, session=None) -> bytes:
    session = session or requests
    last: Exception | None = None
    for i in range(attempts):
        try:
            r = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
            r.raise_for_status()
            return r.content
        except Exception as e:  # noqa: BLE001 - any failure is retried, then reported
            last = e
            if i < attempts - 1:
                sleep(backoff * 2**i)
    raise FetchError(f"{url}: {last}")
