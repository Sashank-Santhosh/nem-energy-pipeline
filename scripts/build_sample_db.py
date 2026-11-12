"""Usage: uv run python scripts/build_sample_db.py OUT.duckdb"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest.sample import build_sample  # noqa: E402

if __name__ == "__main__":
    print(build_sample(Path(sys.argv[1] if len(sys.argv) > 1 else "sample.duckdb")))
