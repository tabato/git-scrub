"""CLI entry point."""
import json
import subprocess
import sys

import click
import requests
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from . import __version__
from .github import count_email_in_repo, get_token, list_repos, verify_clean
from .rewriter import check_prerequisites, cloned_repo, filter_email, force_push_all

console = Console()
err_console = Console(stderr=True)


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
    "--branch", default=None, metavar="NAME",
    help="Branch to scan (default: each repo's default branch).",
)
@click.option(
    "--fix", is_flag=True, default=False,
    help="Rewrite history and force-push. Default is dry-run.",
)
@click.option(
    "--dry-run", "dry_run", is_flag=True, default=False,
    help="Explicit dry-run flag — scan only, no changes (this is already the default).",
)
@click.option(
    "--yes", "-y", is_flag=True, default=False,
    help="Skip per-repo confirmation prompts.",
)
@click.option(
    "--json", "json_output", is_flag=True, default=False,
    help="Output results as JSON (suppresses all other output).",
)
@click.option(
    "--token", default=None, envvar="GITHUB_TOKEN", show_envvar=True,
    help="GitHub token. Falls back to `gh auth token`.",
)
def main(old_email, new_email, org, users, repos, branch, fix, dry_run, yes, json_output, token):
    """Scan GitHub orgs and user profiles for a committed email address.

    Checks both author and committer email fields in every commit.
    Dry-run by default — add --fix to rewrite and force-push.

    \b
    Examples:
      git-scrub --old-email old@work.edu --org my-org
      git-scrub --old-email old@work.edu --user myusername
      git-scrub --old-email old@work.edu --org org1 --org org2 --user myusername
      git-scrub --old-email old@work.edu --new-email me@users.noreply.github.com \\
                --org my-org --fix
      git-scrub --old-email old@work.edu --org my-org --json
    """
    if fix and dry_run:
        raise click.UsageError("--fix and --dry-run are mutually exclusive.")
    if fix and not new_email:
        raise click.UsageError("--new-email is required when using --fix.")
    if not org and not users and not repos:
        raise click.UsageError("Specify at least one of --org, --user, or --repo.")

    quiet = json_output  # suppress rich output when --json is set

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

    if not quiet:
        console.print()

    for name in org:
        if not quiet:
            console.print(f"  Fetching [bold]{name}[/bold] (org) ...", end=" ")
        try:
            found = list_repos(name, "org", resolved_token)
            all_repos.extend(found)
            if not quiet:
                console.print(f"[cyan]{len(found)} repos[/cyan]")
        except requests.HTTPError as e:
            if not quiet:
                console.print(f"[red]error ({e.response.status_code})[/red]")

    for name in users:
        if not quiet:
            console.print(f"  Fetching [bold]{name}[/bold] (user) ...", end=" ")
        try:
            found = list_repos(name, "user", resolved_token)
            all_repos.extend(found)
            if not quiet:
                console.print(f"[cyan]{len(found)} repos[/cyan]")
        except requests.HTTPError as e:
            if not quiet:
                console.print(f"[red]error ({e.response.status_code})[/red]")

    all_repos = list(dict.fromkeys(all_repos))  # deduplicate, preserve order
    if not all_repos:
        if not quiet:
            console.print("\n  [yellow]No repos found.[/yellow]")
        else:
            click.echo(json.dumps({"scanned": 0, "dirty": []}))
        return

    # ── Scan ─────────────────────────────────────────────────────────────────
    if not quiet:
        branch_note = f" on [bold]{branch}[/bold]" if branch else ""
        console.print(
            f"\n  Scanning [bold]{len(all_repos)}[/bold] repos for "
            f"[yellow]{old_email}[/yellow]{branch_note} ...\n"
        )

    dirty: list[tuple[str, int]] = []

    if quiet:
        for r in all_repos:
            try:
                n = count_email_in_repo(r, old_email, resolved_token, branch)
                if n:
                    dirty.append((r, n))
            except requests.HTTPError:
                pass
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("  [progress.description]{task.description}"),
            BarColumn(bar_width=36),
            MofNCompleteColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Scanning...", total=len(all_repos))
            for r in all_repos:
                progress.update(task, description=f"[dim]{r}[/dim]")
                try:
                    n = count_email_in_repo(r, old_email, resolved_token, branch)
                    if n:
                        dirty.append((r, n))
                except requests.HTTPError:
                    pass
                progress.advance(task)

    # ── JSON output ───────────────────────────────────────────────────────────
    if quiet:
        result: dict = {
            "scanned": len(all_repos),
            "dirty": [{"repo": r, "commits": n} for r, n in dirty],
        }
        if fix and dirty:
            results = _fix_repos(dirty, old_email, new_email, resolved_token, branch, yes=True, quiet=True)
            result["fixed"] = results
        click.echo(json.dumps(result, indent=2))
        return

    # ── Rich report ───────────────────────────────────────────────────────────
    if not dirty:
        console.print(
            Panel(
                f"[green bold]All {len(all_repos)} repos are clean.[/green bold]\n"
                f"[dim]{old_email}[/dim] was not found in any commit.",
                border_style="green",
                padding=(0, 2),
            )
        )
        return

    table = Table(
        box=box.ROUNDED,
        border_style="yellow",
        show_header=True,
        header_style="bold yellow",
        padding=(0, 1),
    )
    table.add_column("Repository", style="white")
    table.add_column("Commits", justify="right", style="red bold")
    for r, n in dirty:
        table.add_row(r, str(n))

    console.print(table)
    console.print()

    if not fix:
        console.print(
            Panel(
                Text.assemble(
                    ("Dry-run — no changes made.\n", "bold"),
                    ("Re-run with ", "dim"),
                    ("--fix --new-email <addr>", "bold cyan"),
                    (" to rewrite and force-push.", "dim"),
                ),
                border_style="dim",
                padding=(0, 2),
            )
        )
        return

    # ── Fix ───────────────────────────────────────────────────────────────────
    console.print(
        f"  [yellow]{old_email}[/yellow] → [green]{new_email}[/green]\n"
    )

    results = _fix_repos(dirty, old_email, new_email, resolved_token, branch, yes, quiet=False)

    success = [r for r, s in results if s == "cleaned"]
    skipped = [r for r, s in results if s == "skipped"]
    failed  = [r for r, s in results if s == "failed"]

    # ── Summary ───────────────────────────────────────────────────────────────
    summary = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    summary.add_column(style="dim")
    summary.add_column(style="bold")
    summary.add_row("Cleaned", f"[green]{len(success)}[/green]")
    if skipped:
        summary.add_row("Skipped", f"[yellow]{len(skipped)}[/yellow]")
    if failed:
        summary.add_row("Failed", f"[red]{len(failed)}[/red]")
        for r in failed:
            summary.add_row("", f"[red dim]{r}[/red dim]")

    console.print(Panel(summary, title="[bold]Summary[/bold]", border_style="dim", padding=(0, 1)))


# ── Shared fix logic ──────────────────────────────────────────────────────────

def _fix_repos(
    dirty: list[tuple[str, int]],
    old_email: str,
    new_email: str,
    token: str,
    branch: str | None,
    yes: bool,
    quiet: bool,
) -> list[tuple[str, str]]:
    """Rewrite each dirty repo. Returns list of (repo, status) where status is
    'cleaned', 'skipped', or 'failed'."""
    results = []

    for r, n in dirty:
        label = "commit" if n == 1 else "commits"

        if not quiet:
            console.print(f"  [bold]{r}[/bold]  [dim]({n} {label})[/dim]")

        if not yes and not quiet:
            if not click.confirm("    Rewrite and force-push?", default=True):
                console.print("    [yellow]Skipped.[/yellow]\n")
                results.append((r, "skipped"))
                continue

        try:
            if not quiet:
                console.print("    [dim]Cloning ...[/dim]   ", end="")
            with cloned_repo(r) as (repo_dir, clone_url):
                if not quiet:
                    console.print("[green]done[/green]")
                    console.print("    [dim]Rewriting ...[/dim] ", end="")
                filter_email(repo_dir, old_email, new_email)
                if not quiet:
                    console.print("[green]done[/green]")
                    console.print("    [dim]Pushing ...[/dim]   ", end="")
                force_push_all(repo_dir, clone_url)
                if not quiet:
                    console.print("[green]done[/green]")

            if not quiet:
                console.print("    [dim]Verifying ...[/dim] ", end="")
            if verify_clean(r, old_email, token, branch):
                if not quiet:
                    console.print("[green bold]clean ✓[/green bold]")
                results.append((r, "cleaned"))
            else:
                if not quiet:
                    console.print("[red]still dirty — check manually[/red]")
                results.append((r, "failed"))

        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or b"").decode().strip()
            if not quiet:
                console.print(f"\n    [red]Failed: {stderr[:300] or str(e)}[/red]")
            results.append((r, "failed"))
        except Exception as e:
            if not quiet:
                console.print(f"\n    [red]Failed: {e}[/red]")
            results.append((r, "failed"))

        if not quiet:
            console.print()

    return results


def _die(msg: str) -> None:
    err_console.print(f"[red bold]Error:[/red bold] {msg}")
    sys.exit(1)
