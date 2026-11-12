"""Download a NEMWeb archive folder politely and extract its CSVs.

Usage: uv run python scripts/download_archive.py scada data/archive/scada --since 2025-11-01
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest.http import fetch
from ingest.mms import iter_csv_members
from ingest.nemweb import list_files
from ingest.sources import ARCHIVE_FOLDERS, NEMWEB_BASE

DATE = re.compile(r"_(\d{8})(?:_\d{8})?\.zip$", re.IGNORECASE)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=sorted(ARCHIVE_FOLDERS))
    ap.add_argument("out_dir")
    ap.add_argument("--since", default="00000000", help="YYYY-MM-DD")
    a = ap.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    done = out / ".done"
    seen = set(done.read_text().split()) if done.exists() else set()
    since = a.since.replace("-", "")
    for url in list_files(NEMWEB_BASE + ARCHIVE_FOLDERS[a.source]):
        m = DATE.search(url)
        if url in seen or (m and m.group(1) < since):
            continue
        for name, data in iter_csv_members(fetch(url)):
            (out / Path(name).name).write_bytes(data)
        with done.open("a") as f:
            f.write(url + "\n")
        print("done", url.rsplit("/", 1)[-1])


if __name__ == "__main__":
    main()
