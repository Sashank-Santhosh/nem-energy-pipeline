from ingest import nemweb, state
from tests.conftest import FIX, FakeFetch, directory_page

FOLDER = "https://nemweb.com.au/Reports/CURRENT/DispatchIS_Reports/"
F1 = FOLDER + "PUBLIC_DISPATCHIS_202611121630_1.zip"
F2 = FOLDER + "PUBLIC_DISPATCHIS_202611121635_2.zip"
DISPATCH = (FIX / "nemweb" / "dispatchis.zip").read_bytes()


def make_fetch(extra=None):
    pages = {FOLDER: directory_page([F2, F1]), F1: DISPATCH, F2: DISPATCH}
    pages.update(extra or {})
    return FakeFetch(pages)


def count(con, table):
    return con.execute(f"select count(*) from {table}").fetchone()[0]


def test_list_files_returns_sorted_absolute_zip_urls():
    assert nemweb.list_files(FOLDER, fetch=make_fetch()) == [F1, F2]


def test_load_twice_loads_nothing_new(con):
    f = make_fetch()
    r1 = nemweb.load_new_files(con, "dispatch", FOLDER, fetch=f)
    n = count(con, "raw.dispatch_regionsum")
    r2 = nemweb.load_new_files(con, "dispatch", FOLDER, fetch=f)
    assert (r1.loaded, r2.loaded, r2.skipped) == (2, 0, 2)
    assert count(con, "raw.dispatch_regionsum") == n == 10


def test_bad_file_recorded_and_run_continues(con):
    r = nemweb.load_new_files(con, "dispatch", FOLDER, fetch=make_fetch({F1: b"not a zip at all"}))
    assert (r.loaded, r.failed) == (1, 1)
    assert count(con, "raw.load_errors") == 1
    assert not state.already_loaded(con, F1)


def test_max_files_limits_downloads(con):
    f = make_fetch()
    r = nemweb.load_new_files(con, "dispatch", FOLDER, fetch=f, max_files=1)
    assert r.loaded == 1
    assert F2 not in f.requested


def test_raw_has_source_file_and_loaded_at(con):
    nemweb.load_new_files(con, "dispatch", FOLDER, fetch=make_fetch(), max_files=1)
    row = con.execute("select source_file, loaded_at from raw.dispatch_price limit 1").fetchone()
    assert row[0] == F1 and row[1] is not None


def test_keep_filters_rows_before_insert(con):
    nemweb.load_new_files(
        con, "dispatch", FOLDER, fetch=make_fetch(), max_files=1,
        keep=lambda key, df: df[df["regionid"] == "SA1"],
    )
    assert count(con, "raw.dispatch_regionsum") == 1
