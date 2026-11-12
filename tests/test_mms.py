import io
import zipfile
from pathlib import Path

from ingest.mms import iter_csv_members, parse_mms
from ingest.sources import REGIONS

FIX = Path(__file__).parent / "fixtures" / "nemweb"


def test_parse_dispatch_fixture():
    tables = parse_mms((FIX / "dispatchis.zip").read_bytes())
    assert {"DISPATCH.REGIONSUM", "DISPATCH.PRICE"} <= tables.keys()
    rs = tables["DISPATCH.REGIONSUM"]
    assert len(rs) == 5
    assert set(rs["regionid"]) == set(REGIONS)
    assert "totaldemand" in rs.columns
    assert all(isinstance(v, str) for v in rs["totaldemand"])


def test_parse_zip_of_zips():
    inner = (FIX / "dispatchis.zip").read_bytes()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.zip", inner)
        z.writestr("b.zip", inner)
    assert len(list(iter_csv_members(buf.getvalue()))) == 2
    assert len(parse_mms(buf.getvalue())["DISPATCH.REGIONSUM"]) == 10


def test_ignores_comment_and_end_rows():
    data = b'C,NEMP.WORLD,X\nI,A,B,1,X,Y\nD,A,B,1,"1",2\nC,"END OF REPORT",3\n'
    t = parse_mms(data)
    assert list(t) == ["A.B"]
    assert t["A.B"].to_dict("records") == [{"x": "1", "y": "2"}]
