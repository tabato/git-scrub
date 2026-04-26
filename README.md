# git-scrub

CLI tool to scan GitHub organizations and user profiles for a committed email address, then rewrite it out of history across every affected repo.

## Why this exists

`git filter-repo` handles the local rewriting step well, but provides no tooling to discover *which* repos across a GitHub org or profile contain a given email, clone them, push the rewritten history back, and verify the result. `git-scrub` automates the entire workflow.

**Common use case:** you've left a job or graduated, and you want to scrub your old institutional email (`you@company.com`) from every repo you've ever touched across multiple orgs — replacing it with your personal GitHub no-reply address.

## Prerequisites

- Python 3.9+
- [`git-filter-repo`](https://github.com/newren/git-filter-repo)
  ```bash
  brew install git-filter-repo
  # or
  pip install git-filter-repo
  ```
- GitHub CLI (`gh`) authenticated **or** a `GITHUB_TOKEN` env var with `repo` scope

## Installation

```bash
pipx install git-scrub
# or
pip install git-scrub
```

## Usage

### Scan (dry-run, default)

```bash
# Scan a whole org
git-scrub --old-email old@work.edu --org my-org

# Scan all repos under a GitHub username
git-scrub --old-email old@work.edu --user myusername

# Multiple targets at once
git-scrub --old-email old@work.edu --org org1 --org org2 --user myusername

# Target a specific repo
git-scrub --old-email old@work.edu --repo owner/repo-name
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

### Token

```bash
# Via env var
GITHUB_TOKEN=ghp_... git-scrub ...

# Via flag
git-scrub --token ghp_... ...
```

If neither is set, `git-scrub` calls `gh auth token` automatically.

## Notes

- **Dry-run is the default.** Nothing is written without `--fix`.
- The scan checks the **default branch** of each repo. `git filter-repo` rewrites **all branches and tags** when fixing, so the full history is cleaned.
- Force-pushing rewrites history for all collaborators on a repo — coordinate with your team before running on shared repos.
- After a push, GitHub's commit attribution UI may take a short time to reflect the change.

## License

MIT
