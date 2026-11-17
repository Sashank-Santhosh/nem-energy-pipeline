import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_gitattributes_pins_unix_line_endings():
    text = (ROOT / ".gitattributes").read_text()
    assert "eol=lf" in text


def test_tracked_text_files_are_stored_with_unix_line_endings():
    # Windows line endings in a shell script make Linux runners fail, and flipping a file's
    # endings turns a 5-line change into a 500-line diff.
    out = subprocess.run(["git", "ls-files", "--eol"], capture_output=True, text=True,
                         cwd=ROOT, check=True).stdout
    bad = [ln.split("\t")[-1] for ln in out.splitlines() if ln.split()[0] in ("i/crlf", "i/mixed")]
    assert not bad, f"{len(bad)} files not stored with LF, e.g. {bad[:5]}"
