"""Parse AEMO MMS-format CSV files (C = comment, I = header, D = data rows)."""

import csv
import io
import zipfile
from collections.abc import Iterator

import pandas as pd


def iter_csv_members(data: bytes) -> Iterator[tuple[str, bytes]]:
    """Yield (name, csv_bytes) from a CSV, a zip, or a zip of zips."""
    if not zipfile.is_zipfile(io.BytesIO(data)):
        yield "", data
        return
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            inner = z.read(name)
            if zipfile.is_zipfile(io.BytesIO(inner)):
                yield from iter_csv_members(inner)
            else:
                yield name, inner


def parse_mms(data: bytes) -> dict[str, pd.DataFrame]:
    rows: dict[str, list[list[str]]] = {}
    cols: dict[str, list[str]] = {}
    for _, member in iter_csv_members(data):
        key = None
        for rec in csv.reader(io.StringIO(member.decode("utf-8", errors="replace"))):
            if not rec:
                continue
            if rec[0] == "I":
                key = f"{rec[1]}.{rec[2]}".upper()
                cols.setdefault(key, [c.lower() for c in rec[4:]])
                rows.setdefault(key, [])
            elif rec[0] == "D" and key is not None:
                rows[key].append(rec[4:])
    return {k: pd.DataFrame(v, columns=cols[k], dtype=str) for k, v in rows.items()}
