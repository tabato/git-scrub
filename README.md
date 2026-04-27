# git-scrub

[![PyPI version](https://img.shields.io/pypi/v/git-scrub.svg)](https://pypi.org/project/git-scrub/)
[![Python versions](https://img.shields.io/pypi/pyversions/git-scrub.svg)](https://pypi.org/project/git-scrub/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

CLI tool to scan GitHub organizations and user profiles for a committed email address, then rewrite it out of history across every affected repo.

---

## Why this exists

`git filter-repo` handles the local rewriting step well, but provides no tooling to:

- **Discover** which repos across a GitHub org or user profile contain a given email
- **Clone**, rewrite, and force-push each one automatically
- **Verify** the result via the GitHub API after each push
- Report a clean summary across dozens or hundreds of repos

`git-scrub` automates the entire workflow. Point it at an org or a username, give it the old and new email, and it handles the rest.

**Common use case:** you've left a job or graduated, and you want to scrub your old institutional email (`you@university.edu`) from every repo you've ever touched — replacing it with your personal GitHub no-reply address.

---

## How it works

```
1. Discover   →  list every repo in the target org(s) / user profile(s)
2. Scan       →  check each repo's commit history for the old email
                 (both author and committer fields)
3. Report     →  show a table of dirty repos and commit counts
4. Rewrite    →  for each dirty repo: clone → git filter-repo → force-push
5. Verify     →  confirm via the GitHub API that the email is gone
6. Clean up   →  temp clone is deleted after each repo
```

Steps 4–6 only run with `--fix`. Everything up to step 3 is always safe.

---

## Prerequisites

- Python 3.9+
- [`git-filter-repo`](https://github.com/newren/git-filter-repo)
  ```bash
  brew install git-filter-repo
  # or
  pip install git-filter-repo
  ```
- GitHub CLI (`gh`) authenticated **or** a `GITHUB_TOKEN` env var with `repo` scope

---

## Installation

```bash
pipx install git-scrub   # recommended
# or
pip install git-scrub
```

---

## Usage

### Scan (dry-run, always safe)

```bash
# Scan a whole org
git-scrub --old-email old@work.edu --org my-org

# Scan all repos under a GitHub username (public + private)
git-scrub --old-email old@work.edu --user myusername

# Multiple targets at once
git-scrub --old-email old@work.edu --org org1 --org org2 --user myusername

# Target a single specific repo
git-scrub --old-email old@work.edu --repo owner/repo-name

# Scan a non-default branch
git-scrub --old-email old@work.edu --org my-org --branch develop
```

### Rewrite and push (`--fix`)

```bash
git-scrub \
  --old-email old@work.edu \
  --new-email 123456+myusername@users.noreply.github.com \
  --org my-org \
  --fix

# Skip per-repo confirmation prompts
git-scrub ... --fix --yes
```

### JSON output (for scripting / CI)

```bash
git-scrub --old-email old@work.edu --org my-org --json
```

```json
{
  "scanned": 42,
  "dirty": [
    { "repo": "my-org/some-repo", "commits": 7 }
  ]
}
```

### Token

```bash
# Via env var (useful in CI)
GITHUB_TOKEN=ghp_... git-scrub ...

# Via flag
git-scrub --token ghp_... ...
```

If neither is provided, `git-scrub` calls `gh auth token` automatically.

---

## Options

| Flag | Description |
|---|---|
| `--old-email` | Email to find (required) |
| `--new-email` | Replacement email (required with `--fix`) |
| `--org` | GitHub org to scan. Repeatable. |
| `--user` | GitHub username to scan all their repos. Repeatable. |
| `--repo` | Specific `owner/repo` to target. Repeatable. |
| `--branch` | Branch to scan (default: each repo's default branch) |
| `--fix` | Rewrite history and force-push |
| `--dry-run` | Explicit scan-only mode (already the default) |
| `--yes` / `-y` | Skip per-repo confirmation prompts |
| `--json` | Output results as JSON |
| `--token` | GitHub token (or set `GITHUB_TOKEN`) |
| `-V` / `--version` | Print version and exit |

---

## Notes

- **Dry-run is the default.** Nothing is written without `--fix`.
- Both `author` and `committer` email fields are checked and rewritten.
- The scan checks each repo's default branch (or `--branch`). `git filter-repo` rewrites **all branches and tags** when fixing, so the full history is cleaned regardless.
- Force-pushing rewrites history for all collaborators on a repo — coordinate with your team before running on shared repos.
- GitHub's commit attribution UI may take a short time to update after a push.

---

## License

MIT
