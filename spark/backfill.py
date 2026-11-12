"""One-off PySpark job: 13 months of unit-level SCADA -> 5-minute fuel mix per region.

Usage: uv run python -m spark.backfill --scada-dir data/archive/scada --registration FILE
                                       --out data/fuel_mix.parquet
"""

import argparse
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from ingest.fuel_map import load_fuel_map
from ingest.sources import SCADA_POS


def build_fuel_mix(spark: SparkSession, csv_glob: str, fuel_map: pd.DataFrame) -> DataFrame:
    # MMS files mix row widths, so read lines as text and split, rather than as CSV.
    parts = F.split(F.col("value"), ",")
    unq = lambda i: F.regexp_replace(parts.getItem(i), '"', "")
    rows = (spark.read.text(csv_glob)
            .where((parts.getItem(0) == "D") & (parts.getItem(2) == "UNIT_SCADA"))
            .select(unq(SCADA_POS["settlementdate"]).alias("settlementdate"),
                    unq(SCADA_POS["duid"]).alias("duid"),
                    unq(SCADA_POS["scadavalue"]).cast("double").alias("mw")))
    fmap = spark.createDataFrame(fuel_map[["duid", "regionid", "fuel"]])
    return (rows.join(F.broadcast(fmap), "duid", "left")
            .fillna({"regionid": "UNKNOWN", "fuel": "other", "mw": 0.0})
            .groupBy("settlementdate", "regionid", "fuel")
            .agg(F.sum("mw").alias("mw")))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scada-dir", required=True)
    ap.add_argument("--registration", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    fmap = load_fuel_map(Path(a.registration).read_bytes())
    spark = (SparkSession.builder.master("local[*]").appName("nem-backfill")
             .config("spark.driver.memory", "4g").getOrCreate())
    try:
        result = build_fuel_mix(spark, str(Path(a.scada_dir) / "*.CSV"), fmap)
        # toArrow + pyarrow avoids Hadoop's Windows file writer (which needs winutils).
        pq.write_table(result.toArrow(), a.out)
    finally:
        spark.stop()
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
