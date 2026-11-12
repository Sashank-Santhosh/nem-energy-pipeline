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
    assert keep("x/PUBLIC_PREDISPATCHIS_202611121200_20261112113100.zip")
    assert keep("x/PUBLIC_PREDISPATCHIS_202611121230_20261112120100.zip")
    assert not keep("x/PUBLIC_PREDISPATCHIS_202611121630_20261112160155.zip")


def test_sample_db_creates_missing_folder(tmp_path):
    out = tmp_path / "new" / "dir" / "s.duckdb"
    build_sample(out)
    assert out.exists()
