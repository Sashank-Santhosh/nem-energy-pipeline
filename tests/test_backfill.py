import shutil
import zipfile

import pandas as pd
import pytest

from ingest.fuel_map import aggregate_scada, load_fuel_map
from ingest.mms import parse_mms
from tests.conftest import FIX

pytestmark = pytest.mark.skipif(shutil.which("java") is None, reason="Spark needs Java 17")


def test_build_fuel_mix_matches_pandas(tmp_path):
    from pyspark.sql import SparkSession

    from spark.backfill import build_fuel_mix

    raw = (FIX / "nemweb" / "dispatchscada.zip").read_bytes()
    with zipfile.ZipFile(FIX / "nemweb" / "dispatchscada.zip") as z:
        z.extractall(tmp_path)
    fmap = load_fuel_map((FIX / "registration_sample.xlsx").read_bytes())
    expected = aggregate_scada(parse_mms(raw)["DISPATCH.UNIT_SCADA"], fmap)

    spark = SparkSession.builder.master("local[1]").appName("test").getOrCreate()
    try:
        got = build_fuel_mix(spark, str(tmp_path / "*.CSV"), fmap).toPandas()
    finally:
        spark.stop()
    key = ["settlementdate", "regionid", "fuel"]
    e = expected.sort_values(key).reset_index(drop=True)
    g = got.sort_values(key).reset_index(drop=True)
    pd.testing.assert_frame_equal(g[key], e[key])
    assert g["mw"].round(3).tolist() == e["mw"].round(3).tolist()
