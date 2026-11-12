import pandas as pd
import pytest

from ingest.fuel_map import aggregate_scada, classify_fuel, load_fuel_map
from tests.conftest import FIX


@pytest.mark.parametrize(
    "primary, descriptor, expected",
    [
        ("Solar", "Solar", "solar"),
        ("Solar", "solar", "solar"),
        ("Wind", "Wind", "wind"),
        ("Hydro", "Water", "hydro"),
        ("Battery Storage", "Grid", "battery"),
        ("Fossil", "Black Coal", "coal"),
        ("Fossil", "Brown Coal", "coal"),
        ("Fossil", "Natural Gas", "gas"),
        ("Fossil", "Coal Seam Methane", "gas"),
        ("Fossil", "Waste Coal Mine Gas", "gas"),
        ("Fossil", "Natrual Gas/ Diesel", "gas"),
        ("Fossil", "Diesel", "other"),
        ("Renewable/ Biomass / Waste", "Bagasse", "other"),
        ("-", "-", "other"),
    ],
)
def test_classify_fuel(primary, descriptor, expected):
    assert classify_fuel(primary, descriptor) == expected


def test_load_fuel_map_from_sample():
    m = load_fuel_map((FIX / "registration_sample.xlsx").read_bytes())
    assert list(m.columns) == ["duid", "regionid", "fuel"]
    assert m["duid"].is_unique
    assert set(m["fuel"]) <= {"solar", "wind", "coal", "gas", "hydro", "battery", "other"}
    assert {"solar", "wind", "coal", "gas", "hydro", "battery"} <= set(m["fuel"])


def test_aggregate_scada_sums_by_region_and_fuel():
    fmap = pd.DataFrame({"duid": ["A", "B", "C"], "regionid": ["SA1", "SA1", "VIC1"],
                         "fuel": ["wind", "wind", "coal"]})
    scada = pd.DataFrame({"settlementdate": ["t"] * 4, "duid": ["A", "B", "C", "C"],
                          "scadavalue": ["10.5", "4.5", "100", "-1"]})
    out = aggregate_scada(scada, fmap).sort_values("regionid").reset_index(drop=True)
    assert out.to_dict("records") == [
        {"settlementdate": "t", "regionid": "SA1", "fuel": "wind", "mw": 15.0},
        {"settlementdate": "t", "regionid": "VIC1", "fuel": "coal", "mw": 99.0},
    ]


def test_unknown_duid_is_other():
    fmap = pd.DataFrame({"duid": ["A"], "regionid": ["SA1"], "fuel": ["wind"]})
    scada = pd.DataFrame({"settlementdate": ["t"], "duid": ["ZZZ"], "scadavalue": ["3"]})
    out = aggregate_scada(scada, fmap)
    assert out.to_dict("records") == [
        {"settlementdate": "t", "regionid": "UNKNOWN", "fuel": "other", "mw": 3.0}
    ]
