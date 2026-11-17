"""Render every dashboard page and fail on any error.

Run it in an environment built from requirements.txt alone (what Streamlit Cloud installs),
so a missing or too-new package is caught before it reaches the live site:

    uv run --isolated --no-project --python 3.12 --with-requirements requirements.txt \\
        python scripts/check_dashboard.py data/ci.duckdb

--isolated matters: without it uv reuses the project's own .venv, where every package is
installed, and a package missing from requirements.txt would go unnoticed.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PAGES = ["dashboard/app.py", "dashboard/pages/1_Solar_and_the_grid.py",
         "dashboard/pages/2_Forecast_accuracy.py"]


def main(db_path: str) -> int:
    if Path(sys.prefix).resolve().is_relative_to(ROOT.resolve()):
        print("Refusing to run inside the project environment: it has every package installed, "
              "so this check could not catch a missing one. Use `uv run --isolated`.")
        return 2
    os.environ["NEM_DB_PATH"] = str(Path(db_path).resolve())
    from streamlit.testing.v1 import AppTest

    from dashboard import copy

    failed = 0
    for page in PAGES:
        at = AppTest.from_file(str(ROOT / page), default_timeout=90).run()
        text = " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)
        problems = [str(e.value)[:200] for e in at.exception]
        for needed in (copy.ATTRIBUTION, copy.DISCLAIMER, copy.REFRESH_NOTE):
            if needed not in text:
                problems.append(f"missing required text: {needed[:40]}...")
        print(f"{'FAIL' if problems else 'ok  '} {page}", *problems, sep="\n  " if problems else "")
        failed += bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
