"""Map generator units (DUIDs) to fuel types and aggregate unit output."""

import io

import pandas as pd

from ingest.sources import REGISTRATION_SHEET

GAS_WORDS = ("gas", "methane", "ethane")


def classify_fuel(fuel_source_primary: str, fuel_source_descriptor: str) -> str:
    p = str(fuel_source_primary).strip().lower()
    d = str(fuel_source_descriptor).strip().lower()
    if p.startswith("solar"):
        return "solar"
    if p.startswith("wind"):
        return "wind"
    if p.startswith("hydro"):
        return "hydro"
    if p.startswith("battery"):
        return "battery"
    if p == "fossil":
        if d in ("black coal", "brown coal"):
            return "coal"
        if any(w in d for w in GAS_WORDS):
            return "gas"
    return "other"


def load_fuel_map(xlsx: bytes) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(xlsx), sheet_name=REGISTRATION_SHEET)
    out = pd.DataFrame({
        "duid": df["DUID"].astype(str).str.strip(),
        "regionid": df["Region"].astype(str).str.strip(),
        "fuel": [classify_fuel(p, d) for p, d in
                 zip(df["Fuel Source - Primary"], df["Fuel Source - Descriptor"])],
    })
    out = out[out["duid"].ne("") & out["duid"].ne("nan") & out["duid"].ne("-")]
    return out.drop_duplicates("duid").reset_index(drop=True)


def aggregate_scada(scada: pd.DataFrame, fuel_map: pd.DataFrame) -> pd.DataFrame:
    df = scada[["settlementdate", "duid", "scadavalue"]].merge(fuel_map, on="duid", how="left")
    df["regionid"] = df["regionid"].fillna("UNKNOWN")
    df["fuel"] = df["fuel"].fillna("other")
    df["mw"] = pd.to_numeric(df["scadavalue"], errors="coerce").fillna(0.0)
    return (df.groupby(["settlementdate", "regionid", "fuel"], as_index=False)["mw"].sum())
