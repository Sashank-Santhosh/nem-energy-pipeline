import pytest

from ingest.http import FetchError, fetch
from ingest.sources import USER_AGENT


class FakeResp:
    def __init__(self, content=b"", status=200):
        self.content, self.status_code = content, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, fails):
        self.fails, self.calls = fails, []

    def get(self, url, headers=None, timeout=None):
        self.calls.append(headers)
        if len(self.calls) <= self.fails:
            return FakeResp(status=503)
        return FakeResp(b"ok")


def test_fetch_retries_then_succeeds():
    sleeps = []
    s = FakeSession(fails=2)
    assert fetch("u", session=s, sleep=sleeps.append) == b"ok"
    assert sleeps == [2.0, 4.0]


def test_fetch_raises_after_three_failures():
    with pytest.raises(FetchError):
        fetch("u", session=FakeSession(fails=9), sleep=lambda s: None)


def test_fetch_sends_user_agent():
    s = FakeSession(fails=0)
    fetch("u", session=s, sleep=lambda s: None)
    assert s.calls[0]["User-Agent"] == USER_AGENT
