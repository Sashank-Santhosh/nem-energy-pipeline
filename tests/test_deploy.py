import re
from pathlib import Path

from dashboard import data

ROOT = Path(__file__).resolve().parent.parent


def requirement_names() -> set[str]:
    lines = (ROOT / "requirements.txt").read_text().splitlines()
    return {re.split(r"[<>=!~\[ ;]", ln.strip(), maxsplit=1)[0].lower().replace("_", "-")
            for ln in lines if ln.strip() and not ln.startswith("#")}


def test_dashboard_requirements_are_slim_and_complete():
    names = requirement_names()
    assert {"streamlit", "plotly", "duckdb", "pandas", "requests"} <= names
    # Build and forecast tools are not needed to show the dashboard and slow the cold start.
    assert not names & {"dbt-duckdb", "dbt-core", "lightgbm", "scikit-learn", "pyspark"}


def test_default_database_url_points_at_the_public_release(monkeypatch):
    monkeypatch.delenv("NEM_DB_URL", raising=False)
    assert data.default_db_url() == (
        "https://github.com/Sashank-Santhosh/nem-energy-pipeline/releases/download/"
        "data-latest/nem.duckdb")
    monkeypatch.setenv("NEM_DB_URL", "https://example.invalid/x.duckdb")
    assert data.default_db_url() == "https://example.invalid/x.duckdb"


def test_dashboard_avoids_removed_streamlit_options():
    for path in (ROOT / "dashboard").rglob("*.py"):
        assert "use_container_width" not in path.read_text(encoding="utf-8"), path.name
    assert "streamlit>=1.50" in (ROOT / "requirements.txt").read_text()
