from pathlib import Path

import pytest
import yaml

WORKFLOWS = sorted((Path(__file__).resolve().parent.parent / ".github" / "workflows").glob("*.yml"))


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_is_valid_yaml_with_jobs(path):
    doc = yaml.safe_load(path.read_text())
    assert doc.get("jobs")


def test_writers_share_one_concurrency_group():
    groups = {p.name: yaml.safe_load(p.read_text()).get("concurrency", {}).get("group")
              for p in WORKFLOWS if p.name in ("collect.yml", "forecast.yml")}
    assert groups == {"collect.yml": "nem-db", "forecast.yml": "nem-db"}


def test_workflows_run_shell_scripts_through_bash():
    # Git on Windows doesn't keep the executable bit, so Linux runners need `bash script.sh`.
    for p in WORKFLOWS:
        for line in p.read_text().splitlines():
            if "scripts/" in line and ".sh" in line:
                assert "bash scripts/" in line, f"{p.name}: {line.strip()}"


def test_hourly_job_makes_the_daily_forecast():
    collect = yaml.safe_load((WORKFLOWS[0].parent / "collect.yml").read_text())
    runs = " ".join(str(s.get("run", "")) for s in collect["jobs"]["collect"]["steps"])
    assert "forecast.cli daily-if-due" in runs
    forecast = yaml.safe_load((WORKFLOWS[0].parent / "forecast.yml").read_text())
    assert "schedule" not in forecast.get(True, forecast.get("on", {}))  # manual only now
