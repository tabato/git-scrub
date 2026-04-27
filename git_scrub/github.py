"""GitHub API interactions — repo discovery and commit scanning."""
import os
import subprocess
import time
from typing import Iterator

import requests

BASE = "https://api.github.com"


def get_token(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    if env := os.environ.get("GITHUB_TOKEN"):
        return env
    try:
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise RuntimeError(
            "No GitHub token found. Set GITHUB_TOKEN or run 'gh auth login'."
        )


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _next_url(resp: requests.Response) -> str | None:
    for part in resp.headers.get("Link", "").split(","):
        if 'rel="next"' in part:
            return part.split(";")[0].strip().strip("<>")
    return None


def _get_pages(url: str, token: str, params: dict | None = None) -> Iterator[list]:
    params = {**(params or {}), "per_page": 100}
    while url:
        resp = requests.get(url, headers=_headers(token), params=params)
        if resp.status_code in (403, 429):
            wait = int(resp.headers.get("Retry-After", 60))
            time.sleep(wait)
            continue
        resp.raise_for_status()
        yield resp.json()
        params = {}
        url = _next_url(resp)


def list_repos(owner: str, owner_type: str, token: str) -> list[str]:
    """Return all repo full names for an org or user (including private, forks)."""
    path = f"orgs/{owner}/repos" if owner_type == "org" else f"users/{owner}/repos"
    repos: list[str] = []
    for page in _get_pages(f"{BASE}/{path}", token, {"type": "all"}):
        repos.extend(r["full_name"] for r in page)
    return repos


def count_email_in_repo(
    repo: str, email: str, token: str, branch: str | None = None
) -> int:
    """Count commits whose author or committer email matches.

    Checks the default branch unless `branch` is specified.
    """
    count = 0
    url = f"{BASE}/repos/{repo}/commits"
    params = {"sha": branch} if branch else {}
    try:
        for page in _get_pages(url, token, params):
            for commit in page:
                c = commit.get("commit", {})
                if (
                    c.get("author", {}).get("email") == email
                    or c.get("committer", {}).get("email") == email
                ):
                    count += 1
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 409:
            pass  # empty repo — not an error
        else:
            raise
    return count


def verify_clean(
    repo: str, email: str, token: str, branch: str | None = None
) -> bool:
    return count_email_in_repo(repo, email, token, branch) == 0
