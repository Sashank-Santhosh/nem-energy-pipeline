"""Discover and load new NEMWeb files into append-only raw tables."""

import contextlib
import re
from dataclasses import dataclass
from datetime import datetime

from ingest import state
from ingest.fuel_map import aggregate_scada
from ingest.http import fetch as default_fetch
from ingest.mms import parse_mms
from ingest.sources import NEMWEB_BASE, TABLES

HREF = re.compile(r'href="([^"]+\.zip)"', re.IGNORECASE)


@dataclass
class LoadResult:
    loaded: int = 0
    skipped: int = 0
    failed: int = 0


def list_files(folder_url: str, fetch=default_fetch) -> list[str]:
    html = fetch(folder_url).decode("utf-8", errors="replace")
    return sorted({NEMWEB_BASE + h if h.startswith("/") else h for h in HREF.findall(html)})


def load_new_files(con, source: str, folder_url: str, fetch=default_fetch,
                   max_files: int | None = None, keep=None, fuel_map=None,
                   url_filter=None) -> LoadResult:
    state.ensure_schema(con)
    result = LoadResult()
    for url in list_files(folder_url, fetch=fetch):
        if url_filter is not None and not url_filter(url):
            continue
        if state.already_loaded(con, url):
            result.skipped += 1
            continue
        if max_files is not None and result.loaded + result.failed >= max_files:
            break
        try:
            tables = parse_mms(fetch(url))
            if not any(k in tables for k in TABLES[source]):
                raise ValueError("no expected tables in file")
            rows = 0
            loaded_at = datetime.now()
            con.execute("begin")
            for key, target in TABLES[source].items():
                df = tables.get(key)
                if df is None:
                    continue
                if keep is not None:
                    df = keep(key, df)
                if source == "scada":
                    if fuel_map is None:
                        raise ValueError("scada needs a fuel_map")
                    df = aggregate_scada(df, fuel_map)
                df = df.assign(source_file=url, loaded_at=loaded_at)
                rows += state.append(con, target, df)
            state.mark_loaded(con, source, url, rows)
            con.execute("commit")
            result.loaded += 1
        except Exception as e:  # noqa: BLE001 - a bad file must not stop the run
            with contextlib.suppress(Exception):  # failed before the transaction began
                con.execute("rollback")
            state.record_error(con, source, url, f"{type(e).__name__}: {e}")
            result.failed += 1
    return result
