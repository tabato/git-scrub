"""Clone → filter-repo → force-push pipeline."""
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

REQUIRED_TOOLS = ("git", "git-filter-repo")


def check_prerequisites() -> None:
    missing = [t for t in REQUIRED_TOOLS if not shutil.which(t)]
    if missing:
        raise RuntimeError(
            f"Missing required tool(s): {', '.join(missing)}.\n"
            "  Install git-filter-repo: https://github.com/newren/git-filter-repo\n"
            "  (brew install git-filter-repo  or  pip install git-filter-repo)"
        )


@contextmanager
def cloned_repo(repo: str):
    """Clone repo to a temp dir, yield (repo_dir, clone_url), clean up on exit."""
    tmpdir = Path(tempfile.mkdtemp(prefix="git-scrub-"))
    repo_dir = tmpdir / "repo"
    clone_url = f"https://github.com/{repo}.git"
    try:
        _run(["git", "clone", "--quiet", clone_url, str(repo_dir)])
        yield repo_dir, clone_url
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def filter_email(repo_dir: Path, old_email: str, new_email: str) -> None:
    """Rewrite every commit in every branch/tag to replace old_email with new_email."""
    mailmap = repo_dir / ".git-scrub-mailmap"
    mailmap.write_text(f" <{new_email}> <{old_email}>\n")
    _run(
        [
            "git-filter-repo",
            "--mailmap", str(mailmap),
            "--force",
        ],
        cwd=repo_dir,
    )


def force_push_all(repo_dir: Path, remote_url: str) -> None:
    """Re-attach origin and force-push all branches and tags."""
    _run(["git", "remote", "add", "origin", remote_url], cwd=repo_dir)
    _run(["git", "push", "origin", "--force", "--all", "--quiet"], cwd=repo_dir)
    _run(["git", "push", "origin", "--force", "--tags", "--quiet"], cwd=repo_dir)


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, check=True, capture_output=True, cwd=cwd)
