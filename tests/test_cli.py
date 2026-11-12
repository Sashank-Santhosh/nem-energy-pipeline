import json

import duckdb

from ingest import cli
from ingest.sample import build_sample

RAW = {"raw.dispatch_regionsum", "raw.dispatch_price", "raw.rooftop_pv_actual", "raw.fuel_mix",
       "raw.predispatch_regionsum", "raw.weather"}


def test_collect_without_db_requires_init(tmp_path):
    db = tmp_path / "nem.duckdb"
    assert cli.main(["collect", "--db", str(db)]) == 2
    assert not db.exists()


def test_upload_refused_when_rows_shrink():
    assert cli.safe_to_upload({"raw.x": 10}, {"raw.x": 9}) is False
    assert cli.safe_to_upload({"raw.x": 10}, {"raw.y": 99}) is False
    assert cli.safe_to_upload({"raw.x": 10}, {"raw.x": 10}) is True
    assert cli.safe_to_upload({"raw.x": 10}, {"raw.x": 11, "raw.y": 1}) is True


def test_sample_db_has_all_raw_tables(tmp_path):
    db = tmp_path / "s.duckdb"
    build_sample(db)
    counts = cli.counts(duckdb.connect(str(db), read_only=True))
    assert RAW <= counts.keys()
    assert all(counts[t] > 0 for t in RAW)


def test_counts_command_prints_json(tmp_path, capsys):
    db = tmp_path / "s.duckdb"
    build_sample(db)
    assert cli.main(["counts", "--db", str(db)]) == 0
    assert json.loads(capsys.readouterr().out)["raw.weather"] > 0


def test_predispatch_url_filter_keeps_only_noon_runs():
    keep = cli.predispatch_url_filter
    assert keep("x/PUBLIC_PREDISPATCHIS_202611121300_20261112123206.zip")
    assert keep("x/PUBLIC_PREDISPATCHIS_202611121330_20261112130206.zip")
    assert not keep("x/PUBLIC_PREDISPATCHIS_202611121200_20261112113115.zip")
    assert not keep("x/PUBLIC_PREDISPATCHIS_202611121630_20261112160155.zip")


def test_sample_db_creates_missing_folder(tmp_path):
    out = tmp_path / "new" / "dir" / "s.duckdb"
    build_sample(out)
    assert out.exists()


def test_guard_command_exit_codes(tmp_path):
    old, new, bad = tmp_path / "old.json", tmp_path / "new.json", tmp_path / "bad.json"
    old.write_text('{"raw.x": 5}')
    new.write_text('{"raw.x": 6}')
    bad.write_text('{"raw.x": 4}')
    assert cli.main(["guard", "--old", str(old), "--new", str(new)]) == 0
    assert cli.main(["guard", "--old", str(old), "--new", str(bad)]) == 1


def test_backfill_nemweb_respects_since(tmp_path):
    from pathlib import Path

    from ingest.sources import ARCHIVE_FOLDERS, NEMWEB_BASE

    fix = Path(__file__).parent / "fixtures" / "nemweb" / "dispatchis.zip"
    folder = NEMWEB_BASE + ARCHIVE_FOLDERS["dispatch"]
    old, new = folder + "PUBLIC_DISPATCHIS_20251101.zip", folder + "PUBLIC_DISPATCHIS_20260901.zip"
    pages = {folder: f'<a href="{old}">a</a><a href="{new}">b</a>'.encode(),
             old: fix.read_bytes(), new: fix.read_bytes()}
    con = duckdb.connect(str(tmp_path / "b.duckdb"))
    r = cli.backfill_nemweb(con, "dispatch", since="2026-06-01", fetch=lambda u, **_: pages[u])
    assert (r.loaded, con.execute("select count(*) from raw.load_log").fetchone()[0]) == (1, 1)


def test_weather_history_loads_every_region(tmp_path):
    from datetime import date
    from pathlib import Path

    body = (Path(__file__).parent / "fixtures" / "openmeteo" / "archive_adelaide.json").read_bytes()
    con = duckdb.connect(str(tmp_path / "w.duckdb"))
    n = cli.weather_history(con, date(2026, 10, 3), date(2026, 10, 5), "historical_forecast",
                            fetch=lambda u, **_: body)
    assert n == 5 * 72
    kinds = con.execute("select distinct kind from raw.weather").fetchall()
    assert kinds == [("historical_forecast",)]
