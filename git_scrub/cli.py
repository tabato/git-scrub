"""CLI entry point."""
import subprocess
import sys

import click
import requests

from . import __version__
from .github import count_email_in_repo, get_token, list_repos, verify_clean
from .rewriter import check_prerequisites, cloned_repo, filter_email, force_push_all


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-V", "--version", prog_name="git-scrub")
@click.option(
    "--old-email", required=True, metavar="EMAIL",
    help="Email address to scan for and remove.",
)
@click.option(
    "--new-email", default=None, metavar="EMAIL",
    help="Replacement email address (required with --fix).",
)
@click.option(
    "--org", multiple=True, metavar="NAME",
    help="GitHub org to scan. Repeatable.",
)
@click.option(
    "--user", "users", multiple=True, metavar="NAME",
    help="GitHub username — scans all their repos. Repeatable.",
)
@click.option(
    "--repo", "repos", multiple=True, metavar="OWNER/REPO",
    help="Specific repo to target. Repeatable.",
)
@click.option(
    "--fix", is_flag=True, default=False,
    help="Rewrite history and force-push. Default is dry-run.",
)
@click.option(
    "--yes", "-y", is_flag=True, default=False,
    help="Skip per-repo confirmation prompts.",
)
@click.option(
    "--token", default=None, envvar="GITHUB_TOKEN", show_envvar=True,
    help="GitHub token. Falls back to `gh auth token`.",
)
def main(old_email, new_email, org, users, repos, fix, yes, token):
    """Scan GitHub orgs and user profiles for a committed email address.

    Dry-run by default — add --fix to rewrite and force-push.

    \b
    Examples:
      git-scrub --old-email old@work.edu --org my-org
      git-scrub --old-email old@work.edu --user myusername
      git-scrub --old-email old@work.edu --org org1 --org org2 --user myusername
      git-scrub --old-email old@work.edu --new-email me@users.noreply.github.com \\
                --org my-org --fix
    """
    if fix and not new_email:
        raise click.UsageError("--new-email is required when using --fix.")
    if not org and not users and not repos:
        raise click.UsageError("Specify at least one of --org, --user, or --repo.")

    if fix:
        try:
            check_prerequisites()
        except RuntimeError as e:
            _die(str(e))

    try:
        resolved_token = get_token(token)
    except RuntimeError as e:
        _die(str(e))

    # ── Collect repos ────────────────────────────────────────────────────────
    all_repos: list[str] = list(repos)

    for name in org:
        click.echo(f"Fetching repos  org  {click.style(name, bold=True)} ... ", nl=False)
        try:
            found = list_repos(name, "org", resolved_token)
            all_repos.extend(found)
            click.echo(click.style(f"{len(found)} repos", fg="cyan"))
        except requests.HTTPError as e:
            click.echo(click.style(f"error ({e.response.status_code})", fg="red"))

    for name in users:
        click.echo(f"Fetching repos  user {click.style(name, bold=True)} ... ", nl=False)
        try:
            found = list_repos(name, "user", resolved_token)
            all_repos.extend(found)
            click.echo(click.style(f"{len(found)} repos", fg="cyan"))
        except requests.HTTPError as e:
            click.echo(click.style(f"error ({e.response.status_code})", fg="red"))

    all_repos = list(dict.fromkeys(all_repos))  # deduplicate, preserve order
    if not all_repos:
        click.echo("No repos to scan.")
        return

    # ── Scan ─────────────────────────────────────────────────────────────────
    click.echo(
        f"\nScanning {click.style(str(len(all_repos)), bold=True)} repos for "
        f"{click.style(old_email, fg='yellow')} ...\n"
    )

    dirty: list[tuple[str, int]] = []
    with click.progressbar(
        all_repos, label="  Progress", show_pos=True, width=40, show_percent=True
    ) as bar:
        for r in bar:
            try:
                n = count_email_in_repo(r, old_email, resolved_token)
                if n:
                    dirty.append((r, n))
            except requests.HTTPError:
                pass  # silently skip repos we can't read

    click.echo()

    if not dirty:
        click.echo(click.style("  All clean — nothing found.", fg="green", bold=True))
        return

    # ── Report ────────────────────────────────────────────────────────────────
    click.echo(click.style(f"  {len(dirty)} dirty repo(s):\n", fg="yellow", bold=True))
    pad = max(len(r) for r, _ in dirty)
    for r, n in dirty:
        label = "commit" if n == 1 else "commits"
        click.echo(f"    {click.style('✗', fg='red')}  {r:<{pad}}  {n} {label}")

    if not fix:
        click.echo(
            f"\n  {click.style('Dry-run — no changes made.', bold=True)}\n"
            f"  Re-run with {click.style('--fix --new-email <addr>', bold=True)} to rewrite.\n"
        )
        return

    # ── Fix ───────────────────────────────────────────────────────────────────
    click.echo(
        f"\n  {click.style(old_email, fg='yellow')} → {click.style(new_email, fg='green')}\n"
    )

    success, skipped, failed = [], [], []

    for r, n in dirty:
        label = "commit" if n == 1 else "commits"
        click.echo(click.style(f"  {r}", bold=True) + f"  ({n} {label})")

        if not yes and not click.confirm("    Rewrite and force-push?", default=True):
            click.echo("    Skipped.\n")
            skipped.append(r)
            continue

        try:
            click.echo("    Cloning ...    ", nl=False)
            with cloned_repo(r) as (repo_dir, clone_url):
                click.echo(click.style("done", fg="green"))

                click.echo("    Rewriting ...  ", nl=False)
                filter_email(repo_dir, old_email, new_email)
                click.echo(click.style("done", fg="green"))

                click.echo("    Pushing ...    ", nl=False)
                force_push_all(repo_dir, clone_url)
                click.echo(click.style("done", fg="green"))

            click.echo("    Verifying ...  ", nl=False)
            if verify_clean(r, old_email, resolved_token):
                click.echo(click.style("clean ✓", fg="green"))
                success.append(r)
            else:
                click.echo(click.style("still dirty — check manually", fg="red"))
                failed.append(r)

        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or b"").decode().strip()
            click.echo(click.style(f"\n    Failed: {stderr[:300] or str(e)}", fg="red"))
            failed.append(r)
        except Exception as e:
            click.echo(click.style(f"\n    Failed: {e}", fg="red"))
            failed.append(r)

        click.echo()

    # ── Summary ───────────────────────────────────────────────────────────────
    click.echo("  " + "─" * 46)
    click.echo(f"  {click.style('Summary', bold=True)}")
    click.echo(f"    Cleaned : {click.style(str(len(success)), fg='green', bold=True)}")
    if skipped:
        click.echo(f"    Skipped : {click.style(str(len(skipped)), fg='yellow', bold=True)}")
    if failed:
        click.echo(f"    Failed  : {click.style(str(len(failed)), fg='red', bold=True)}")
        for r in failed:
            click.echo(f"               {r}")
    click.echo()


def _die(msg: str) -> None:
    click.echo(click.style(f"Error: {msg}", fg="red"), err=True)
    sys.exit(1)
