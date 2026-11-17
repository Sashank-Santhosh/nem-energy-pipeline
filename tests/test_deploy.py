import importlib.util
import re
import sys
import tomllib
from pathlib import Path

import pytest
import yaml
from packaging.requirements import Requirement
from packaging.version import Version

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


def hosted_requirements() -> list[Requirement]:
    lines = (ROOT / "requirements.txt").read_text().splitlines()
    return [Requirement(ln.strip()) for ln in lines if ln.strip() and not ln.startswith("#")]


def locked_versions() -> dict[str, Version]:
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    return {p["name"]: Version(p["version"]) for p in lock["package"]}


def test_hosted_requirements_allow_the_locked_versions():
    locked = locked_versions()
    for req in hosted_requirements():
        assert req.specifier.contains(locked[req.name], prereleases=True), (req.name, locked[req.name])


def test_duckdb_floor_is_not_older_than_the_version_that_writes_the_database():
    # A database file written by a newer DuckDB cannot be opened by an older one.
    req = next(r for r in hosted_requirements() if r.name == "duckdb")
    floor = max(Version(s.version) for s in req.specifier if s.operator == ">=")
    assert floor >= locked_versions()["duckdb"]


def test_every_hosted_requirement_has_an_upper_limit():
    for req in hosted_requirements():
        assert any(s.operator in ("<", "<=", "==", "~=") for s in req.specifier), req.name


def test_ci_renders_the_dashboard_from_requirements_txt_alone():
    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    runs = " ".join(str(s.get("run", "")) for s in ci["jobs"]["test"]["steps"])
    assert "--isolated" in runs  # else uv reuses the project .venv and hides missing packages
    assert "--with-requirements requirements.txt" in runs
    assert "scripts/check_dashboard.py" in runs


@pytest.mark.skipif(not Path(sys.prefix).resolve().is_relative_to(ROOT.resolve()),
                    reason="only meaningful when tests run inside the project environment")
def test_check_dashboard_refuses_to_run_in_the_project_environment():
    # In the project env every package is installed, so the check could not catch a missing one.
    spec = importlib.util.spec_from_file_location("check_dashboard",
                                                  ROOT / "scripts" / "check_dashboard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main("data/does-not-matter.duckdb") == 2
