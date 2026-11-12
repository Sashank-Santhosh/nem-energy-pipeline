from pathlib import Path

import duckdb
import pytest

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    yield c
    c.close()


def directory_page(urls):
    links = "".join(f'<A HREF="{u.replace("https://nemweb.com.au", "")}">{u}</A><br>' for u in urls)
    return f"<html><body><pre>{links}</pre></body></html>".encode()


class FakeFetch:
    """Serves a dict of url -> bytes and records requested urls."""

    def __init__(self, pages):
        self.pages, self.requested = pages, []

    def __call__(self, url, **_):
        self.requested.append(url)
        if url not in self.pages:
            raise RuntimeError(f"404 {url}")
        return self.pages[url]
