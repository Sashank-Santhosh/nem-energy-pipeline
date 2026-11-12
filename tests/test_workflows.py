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
