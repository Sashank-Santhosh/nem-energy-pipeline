import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (ROOT / "scripts" / "keepalive.sh").as_posix()
IDENT = ["-c", "user.name=test", "-c", "user.email=test@example.invalid"]

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def git(cwd, *args, env=None):
    return subprocess.run(["git", *IDENT, *args], cwd=cwd, capture_output=True, text=True,
                          check=True, env=env).stdout.strip()


def make_repo(tmp_path, days_old):
    """A work repo whose last commit is `days_old` days old, with a bare 'remote' to push to."""
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    work.mkdir()
    git(work, "init", "-q", "-b", "main")
    git(work, "remote", "add", "origin", remote.as_posix())
    (work / "f.txt").write_text("x")
    git(work, "add", "f.txt")
    when = (datetime.now(UTC) - timedelta(days=days_old)).isoformat()
    env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    git(work, "commit", "-q", "-m", "old work", env=env)
    git(work, "push", "-q", "-u", "origin", "main")
    return work, remote


def run_script(work):
    r = subprocess.run(["bash", SCRIPT], cwd=work, capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def commit_count(repo):
    return int(git(repo, "rev-list", "--count", "main"))


def test_old_repo_gets_one_empty_commit_pushed(tmp_path):
    work, remote = make_repo(tmp_path, days_old=40)
    run_script(work)
    assert commit_count(work) == 2
    assert commit_count(remote) == 2  # it reached the remote, which is what counts as activity
    assert "keep scheduled jobs alive" in git(remote, "log", "-1", "--format=%s", "main")


def test_recently_active_repo_is_left_alone(tmp_path):
    work, remote = make_repo(tmp_path, days_old=5)
    assert "nothing to do" in run_script(work)
    assert commit_count(remote) == 1


def test_running_twice_does_not_pile_up_commits(tmp_path):
    work, remote = make_repo(tmp_path, days_old=40)
    run_script(work)
    run_script(work)
    assert commit_count(remote) == 2


def test_collect_workflow_runs_the_keepalive():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "collect.yml").read_text())
    runs = " ".join(str(s.get("run", "")) for s in wf["jobs"]["collect"]["steps"])
    assert "bash scripts/keepalive.sh" in runs
    assert wf["permissions"]["contents"] == "write"  # needed to push the commit


def test_works_from_a_shallow_detached_checkout_like_github_actions(tmp_path):
    _, remote = make_repo(tmp_path, days_old=40)
    shallow = tmp_path / "runner"
    subprocess.run(["git", "clone", "-q", "--depth", "1", remote.as_uri(), str(shallow)], check=True)
    git(shallow, "checkout", "-q", "--detach")
    run_script(shallow)
    assert commit_count(remote) == 2
