"""Command line: collect new data, report row counts, load Parquet backfills."""

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from ingest import nemweb, openmeteo, state
from ingest.fuel_map import load_fuel_map
from ingest.http import fetch as default_fetch
from ingest.sources import ARCHIVE_FOLDERS, FOLDERS, NEMWEB_BASE, REGIONS, REGISTRATION_LIST_URL
from ingest.timeutil import nem_now

# Pre-dispatch runs issued ~12:30 and ~13:00 NEM time: the first runs that cover all of tomorrow
# (earlier runs stop at 04:00). Their first period ends 13:00 / 13:30, i.e. trading-day periods
# 18 and 19 (the trading day starts at 04:00).
NOON_FILE = re.compile(r"PUBLIC_PREDISPATCHIS_\d{8}(1300|1330)_")
NOON_PERIODS = ("18", "19")
ARCHIVE_DATE = re.compile(r"_(\d{8})(?:_\d{8})?\.zip$", re.IGNORECASE)


def predispatch_url_filter(url: str) -> bool:
    return bool(NOON_FILE.search(url))


def predispatch_keep(key: str, df: pd.DataFrame) -> pd.DataFrame:
    return df[df["predispatchseqno"].str[-2:].isin(NOON_PERIODS)]


def counts(con) -> dict[str, int]:
    tables = con.execute("select table_schema || '.' || table_name from information_schema.tables "
                         "where table_schema = 'raw' order by 1").fetchall()
    return {t: con.execute(f"select count(*) from {t}").fetchone()[0] for (t,) in tables}


def safe_to_upload(old: dict[str, int], new: dict[str, int]) -> bool:
    return all(t in new and new[t] >= n for t, n in old.items())


def refresh_fuel_map(con, fetch=default_fetch, max_age_days: int = 7) -> pd.DataFrame:
    """Unit -> fuel lookup. Reference data (replaced, not appended), so it lives in `ref`,
    outside the raw tables the upload guard counts. A failed refresh keeps the old map."""
    state.ensure_schema(con)
    con.execute("create schema if not exists ref")
    con.execute("create table if not exists ref.fuel_map"
                "(duid varchar, regionid varchar, fuel varchar, loaded_at timestamp)")
    age = con.execute("select date_diff('day', max(loaded_at), now()) from ref.fuel_map").fetchone()[0]
    if age is None or age >= max_age_days:
        try:
            fm = load_fuel_map(fetch(REGISTRATION_LIST_URL))
            con.execute("delete from ref.fuel_map")
            con.register("_fm", fm)
            con.execute("insert into ref.fuel_map select duid, regionid, fuel, now() from _fm")
            con.unregister("_fm")
        except Exception as e:  # noqa: BLE001 - keep collecting with the previous map
            state.record_error(con, "fuel_map", REGISTRATION_LIST_URL, f"{type(e).__name__}: {e}")
    return con.execute("select duid, regionid, fuel from ref.fuel_map").df()


def collect(con, fetch=default_fetch, max_files: int | None = None, today: date | None = None) -> dict:
    today = today or nem_now().date()
    fmap = refresh_fuel_map(con, fetch=fetch)
    results = {}
    for source in ("dispatch", "rooftop_pv", "scada", "predispatch"):
        kw = {}
        if source == "predispatch":
            kw = {"url_filter": predispatch_url_filter, "keep": predispatch_keep}
        if source == "scada":
            kw = {"fuel_map": fmap}
        results[source] = nemweb.load_new_files(con, source, NEMWEB_BASE + FOLDERS[source],
                                                fetch=fetch, max_files=max_files, **kw)
    for region in REGIONS:
        for kind, start, end in (("archive", today - timedelta(days=3), today - timedelta(days=1)),
                                 ("forecast", today, today + timedelta(days=1))):
            try:
                df = openmeteo.fetch_temperatures(region, start, end, kind, fetch=fetch)
                openmeteo.load_weather(con, df)
            except Exception as e:  # noqa: BLE001 - weather gaps are tolerated and recorded
                state.record_error(con, f"weather_{kind}", region, f"{type(e).__name__}: {e}")
    return results


def backfill_nemweb(con, source: str, since: str, fetch=default_fetch, fuel_map=None):
    """Load archive files dated on or after `since` (YYYY-MM-DD) for one source."""
    cutoff = since.replace("-", "")

    def recent(url: str) -> bool:
        m = ARCHIVE_DATE.search(url)
        return bool(m) and m.group(1) >= cutoff

    keep = predispatch_keep if source == "predispatch" else None
    return nemweb.load_new_files(con, source, NEMWEB_BASE + ARCHIVE_FOLDERS[source], fetch=fetch,
                                 keep=keep, fuel_map=fuel_map, url_filter=recent)


def weather_history(con, start: date, end: date, kind: str, fetch=default_fetch) -> int:
    rows = 0
    for region in REGIONS:
        df = openmeteo.fetch_temperatures(region, start, end, kind, fetch=fetch)
        rows += openmeteo.load_weather(con, df)
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ingest.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--db", required=True)
    c.add_argument("--init", action="store_true")
    c.add_argument("--max-files", type=int)
    n = sub.add_parser("counts")
    n.add_argument("--db", required=True)
    lp = sub.add_parser("load-parquet")
    lp.add_argument("--db", required=True)
    lp.add_argument("--table", required=True)
    lp.add_argument("--path", required=True)
    bf = sub.add_parser("backfill-nemweb")
    bf.add_argument("--db", required=True)
    bf.add_argument("--source", required=True, choices=sorted(ARCHIVE_FOLDERS))
    bf.add_argument("--since", required=True)
    wh = sub.add_parser("weather-history")
    wh.add_argument("--db", required=True)
    wh.add_argument("--start", required=True, type=date.fromisoformat)
    wh.add_argument("--end", required=True, type=date.fromisoformat)
    wh.add_argument("--kind", required=True, choices=["archive", "historical_forecast"])
    g = sub.add_parser("guard", help="exit 1 if any raw table would shrink")
    g.add_argument("--old", required=True)
    g.add_argument("--new", required=True)
    a = ap.parse_args(argv)

    if a.cmd == "backfill-nemweb":
        with duckdb.connect(a.db) as con:
            r = backfill_nemweb(con, a.source, a.since)
            print(f"{a.source}: loaded={r.loaded} skipped={r.skipped} failed={r.failed}")
        return 0
    if a.cmd == "weather-history":
        with duckdb.connect(a.db) as con:
            print(f"{weather_history(con, a.start, a.end, a.kind)} weather rows")
        return 0
    if a.cmd == "guard":
        old, new = (json.loads(Path(p).read_text()) for p in (a.old, a.new))
        ok = safe_to_upload(old, new)
        print("upload ok" if ok else f"upload refused: {old} -> {new}")
        return 0 if ok else 1

    if a.cmd == "collect":
        if not Path(a.db).exists() and not a.init:
            print(f"{a.db} not found; pass --init to create a new database", file=sys.stderr)
            return 2
        with duckdb.connect(a.db) as con:
            for src, r in collect(con, max_files=a.max_files).items():
                print(f"{src}: loaded={r.loaded} skipped={r.skipped} failed={r.failed}")
        return 0
    if a.cmd == "counts":
        with duckdb.connect(a.db, read_only=True) as con:
            print(json.dumps(counts(con)))
        return 0
    if a.cmd == "load-parquet":
        with duckdb.connect(a.db) as con:
            state.ensure_schema(con)
            df = pd.read_parquet(a.path).assign(source_file=Path(a.path).name,
                                                loaded_at=pd.Timestamp.now())
            print(f"{state.append(con, a.table, df)} rows -> {a.table}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
