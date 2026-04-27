"""CLI validation tests — no network calls required."""
from click.testing import CliRunner

from git_scrub.cli import main


def invoke(*args):
    return CliRunner().invoke(main, list(args))


# ── Argument validation ───────────────────────────────────────────────────────

def test_requires_old_email():
    r = invoke("--org", "myorg")
    assert r.exit_code != 0
    assert "--old-email" in r.output


def test_requires_target():
    r = invoke("--old-email", "old@work.edu")
    assert r.exit_code != 0
    assert "at least one" in r.output


def test_fix_requires_new_email():
    r = invoke("--old-email", "old@work.edu", "--org", "myorg", "--fix")
    assert r.exit_code != 0
    assert "--new-email" in r.output


def test_fix_and_dry_run_are_exclusive():
    r = invoke(
        "--old-email", "old@work.edu",
        "--new-email", "new@example.com",
        "--org", "myorg",
        "--fix", "--dry-run",
    )
    assert r.exit_code != 0
    assert "mutually exclusive" in r.output


def test_help_exits_cleanly():
    r = invoke("--help")
    assert r.exit_code == 0
    assert "--old-email" in r.output
    assert "--fix" in r.output
    assert "--json" in r.output
    assert "--branch" in r.output


def test_version():
    r = invoke("--version")
    assert r.exit_code == 0
    assert "git-scrub" in r.output


# ── GitHub pagination helper ──────────────────────────────────────────────────

from unittest.mock import MagicMock
from git_scrub.github import _next_url


def _mock_resp(link_header):
    resp = MagicMock()
    resp.headers = {"Link": link_header}
    return resp


def test_next_url_parses_correctly():
    link = '<https://api.github.com/repos?page=2>; rel="next", <https://api.github.com/repos?page=5>; rel="last"'
    assert _next_url(_mock_resp(link)) == "https://api.github.com/repos?page=2"


def test_next_url_returns_none_when_no_next():
    link = '<https://api.github.com/repos?page=5>; rel="last"'
    assert _next_url(_mock_resp(link)) is None


def test_next_url_returns_none_on_empty_header():
    assert _next_url(_mock_resp("")) is None
