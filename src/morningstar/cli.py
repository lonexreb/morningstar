"""MorningStar CLI -- the main entry point."""

from __future__ import annotations

import datetime as _dt
import json as _json
import re as _re
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from morningstar import __version__
from morningstar.banner import print_banner
from morningstar.engine import (
    QueueConfig,
    RunState,
    execute_task,
    fetch_prd,
    generate_tasks,
    process_queue,
    read_run_history,
    read_weekly_spend,
    slack_post,
    validate_bot_token,
    validate_model,
    validate_slack_webhook,
)

app = typer.Typer(
    name="morningstar",
    help="Autonomous coding agent powered by Claude Code.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


@app.command()
def run(
    notion_url: str = typer.Option(
        ...,
        "--notion-url",
        "-n",
        help="Notion page URL or ID containing the PRD.",
    ),
    slack_webhook: str = typer.Option(
        None,
        "--slack-webhook",
        "-s",
        envvar="MORNINGSTAR_SLACK_WEBHOOK",
        help="Slack webhook URL. Prefer env var MORNINGSTAR_SLACK_WEBHOOK.",
    ),
    repo: Path = typer.Option(
        ...,
        "--repo",
        "-r",
        help="Path to the target repository.",
        exists=True,
        dir_okay=True,
        file_okay=False,
        resolve_path=True,
    ),
    model: str = typer.Option(
        "sonnet",
        "--model",
        "-m",
        help="Claude model (sonnet, opus, haiku).",
    ),
    budget: float = typer.Option(
        50.0,
        "--budget",
        "-b",
        min=0.01,
        help="Total USD budget for the run.",
    ),
    budget_per_task: float = typer.Option(
        5.0,
        "--task-budget",
        min=0.01,
        help="Max USD per task.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Fetch PRD and generate tasks, but do not execute.",
    ),
    max_tasks: int = typer.Option(
        20,
        "--max-tasks",
        min=1,
        max=100,
        help="Maximum number of tasks to generate.",
    ),
    slack_bot_token: str = typer.Option(
        None,
        "--slack-bot-token",
        envvar="MORNINGSTAR_SLACK_BOT_TOKEN",
        help="Slack bot token (xoxb-...) for two-way Q&A. Prefer env var.",
    ),
    slack_channel: str = typer.Option(
        None,
        "--slack-channel",
        envvar="MORNINGSTAR_SLACK_CHANNEL",
        help="Slack channel ID for posting questions (e.g. C0A2DMV8JNB).",
    ),
    question_timeout: int = typer.Option(
        300,
        "--question-timeout",
        min=30,
        max=1800,
        help="Seconds to wait for Slack answer (default 300).",
    ),
) -> None:
    """Run the autonomous coding agent.

    Reads a PRD from Notion, analyzes the target repo, generates tasks,
    and implements each one using Claude Code CLI.
    """
    print_banner(console)

    # ── Validate inputs ───────────────────────────────────────────
    if not slack_webhook:
        console.print(
            "[bold red]Error:[/bold red] --slack-webhook is required. "
            "Set MORNINGSTAR_SLACK_WEBHOOK env var or pass --slack-webhook."
        )
        raise typer.Exit(1)

    try:
        validate_model(model)
    except ValueError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1) from e

    try:
        validate_slack_webhook(slack_webhook)
    except ValueError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1) from e

    if slack_bot_token:
        try:
            validate_bot_token(slack_bot_token)
        except ValueError as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            raise typer.Exit(1) from e
        if not slack_channel:
            console.print(
                "[bold red]Error:[/bold red] --slack-channel is required when "
                "using --slack-bot-token. Set MORNINGSTAR_SLACK_CHANNEL env var."
            )
            raise typer.Exit(1)
        console.print("  [cyan]Two-way Slack enabled[/cyan] -- will ask questions in channel")

    log_dir = repo / ".agent-logs"
    log_dir.mkdir(exist_ok=True)

    state = RunState()

    # ── Step 1: Fetch PRD ─────────────────────────────────────────
    with console.status("[bold yellow]Fetching PRD from Notion...", spinner="star"):
        slack_post(slack_webhook, "MorningStar started. Reading PRD from Notion...")
        try:
            prd_text, prd_cost = fetch_prd(
                notion_url,
                model=model,
                log_dir=log_dir,
            )
            state.cost += prd_cost
        except RuntimeError as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            slack_post(slack_webhook, f"MorningStar failed: {e}")
            raise typer.Exit(1) from e

    line_count = prd_text.count(chr(10)) + 1
    console.print(f"  [green]PRD fetched[/green] ({line_count} lines, ${prd_cost:.2f})")

    # ── Step 2: Generate tasks ────────────────────────────────────
    with console.status("[bold yellow]Analyzing codebase & generating tasks...", spinner="star"):
        slack_post(slack_webhook, "PRD loaded. Analyzing codebase...")
        try:
            tasks, tasks_cost = generate_tasks(
                prd_text,
                repo_path=repo,
                model=model,
                log_dir=log_dir,
                max_tasks=max_tasks,
            )
            state.cost += tasks_cost
        except RuntimeError as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            slack_post(slack_webhook, f"MorningStar failed: {e}")
            raise typer.Exit(1) from e

    task_count = len(tasks)
    state.tasks = tasks
    console.print(f"  [green]Generated {task_count} tasks[/green] (${tasks_cost:.2f})")
    console.print()

    # Show task list
    task_table = Table(
        title="Task Plan",
        border_style="bright_yellow",
        show_lines=True,
    )
    task_table.add_column("#", style="dim", width=4)
    task_table.add_column("ID", style="cyan")
    task_table.add_column("Title", style="white")

    for i, t in enumerate(tasks, 1):
        task_table.add_row(str(i), t["id"], t.get("title", ""))

    console.print(task_table)
    console.print()

    if dry_run:
        console.print("[bold yellow]Dry run mode[/bold yellow] -- not executing tasks.")
        console.print(f"  Planning cost: [yellow]${state.cost:.2f}[/yellow]")
        slack_post(
            slack_webhook,
            f"MorningStar dry run: {task_count} tasks identified. Cost: ${state.cost:.2f}",
        )
        raise typer.Exit(0)

    # ── Confirmation gate ─────────────────────────────────────────
    if not yes:
        console.print(
            Panel(
                f"MorningStar will execute [bold]{task_count} tasks[/bold] "
                f"in [cyan]{repo}[/cyan]\n"
                f"using Claude Code with "
                f"[bold red]shell access and no human confirmation[/bold red].\n\n"
                f"Budget: [yellow]${budget:.2f}[/yellow] total, "
                f"[yellow]${budget_per_task:.2f}[/yellow] per task.",
                title="[bold bright_yellow]Confirm Execution[/bold bright_yellow]",
                border_style="red",
            )
        )
        confirmed = typer.confirm("Proceed?", default=False)
        if not confirmed:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(0)
        console.print()

    slack_post(slack_webhook, f"Found {task_count} tasks. Starting execution...")

    # ── Step 3: Execute tasks ─────────────────────────────────────
    progress = Progress(
        SpinnerColumn("star", style="yellow"),
        TextColumn("[bold]{task.fields[task_title]}"),
        BarColumn(bar_width=30, style="yellow", complete_style="green"),
        TextColumn("[dim]{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    )

    with progress:
        overall = progress.add_task("Running", total=task_count, task_title="MorningStar")

        for i, task in enumerate(tasks):
            title = task.get("title", task["id"])

            if state.cost >= budget:
                console.print(
                    f"\n[bold red]Budget limit reached[/bold red] "
                    f"(${state.cost:.2f}/${budget:.2f})"
                )
                slack_post(
                    slack_webhook,
                    f"Budget limit (${state.cost:.2f}/${budget:.2f}). Stopping.",
                )
                break

            progress.update(overall, task_title=title)
            slack_post(slack_webhook, f"[{i + 1}/{task_count}] Starting: *{title}*")

            result = execute_task(
                task,
                repo_path=repo,
                model=model,
                budget_per_task=budget_per_task,
                log_dir=log_dir,
                bot_token=slack_bot_token,
                slack_channel=slack_channel,
                slack_webhook=slack_webhook,
                question_timeout=question_timeout,
            )

            state.cost += result.cost

            if result.success:
                state.completed += 1
                slack_post(
                    slack_webhook,
                    f"[{i + 1}/{task_count}] Completed: *{title}* (${result.cost:.2f})",
                )
            else:
                state.failed += 1
                slack_post(
                    slack_webhook,
                    f"[{i + 1}/{task_count}] Failed: *{title}* (${result.cost:.2f})",
                )

            progress.update(overall, advance=1)

    # ── Step 4: Summary ───────────────────────────────────────────
    console.print()

    summary = Table(title="Run Complete", border_style="bright_yellow", show_lines=True)
    summary.add_column("Metric", style="dim")
    summary.add_column("Value", style="bold")

    summary.add_row("Tasks completed", f"[green]{state.completed}[/green]")
    summary.add_row("Tasks failed", f"[red]{state.failed}[/red]")
    summary.add_row("Total cost", f"[yellow]${state.cost:.2f}[/yellow]")
    summary.add_row("Budget", f"${budget:.2f}")
    summary.add_row("Logs", str(log_dir))

    console.print(summary)

    slack_post(
        slack_webhook,
        f"MorningStar complete: *{state.completed}* done, "
        f"*{state.failed}* failed. Cost: ${state.cost:.2f}/{budget:.2f}",
    )


@app.command()
def version() -> None:
    """Show MorningStar version."""
    console.print(f"morningstar {__version__}")


@app.command("process-queue")
def process_queue_cmd(
    repo: Path = typer.Option(
        Path("."),
        "--repo",
        "-r",
        help="Target repository (will be modified and pushed).",
        exists=True,
        dir_okay=True,
        file_okay=False,
        resolve_path=True,
    ),
    model: str = typer.Option("sonnet", "--model", "-m"),
    per_run_budget: float = typer.Option(25.0, "--run-budget", min=0.01),
    per_task_budget: float = typer.Option(5.0, "--task-budget", min=0.01),
    weekly_budget: float = typer.Option(
        200.0,
        "--weekly-budget",
        envvar="MORNINGSTAR_WEEKLY_BUDGET",
        min=0.01,
    ),
    max_tasks: int = typer.Option(20, "--max-tasks", min=1, max=100),
    notion_db_id: str = typer.Option(
        "", "--notion-db-id", envvar="MORNINGSTAR_NOTION_DB_ID"
    ),
    notion_token: str = typer.Option(
        "", "--notion-token", envvar="MORNINGSTAR_NOTION_TOKEN"
    ),
    jira_url: str = typer.Option("", "--jira-url", envvar="MORNINGSTAR_JIRA_URL"),
    jira_email: str = typer.Option("", "--jira-email", envvar="MORNINGSTAR_JIRA_EMAIL"),
    jira_token: str = typer.Option("", "--jira-token", envvar="MORNINGSTAR_JIRA_TOKEN"),
    jira_project_key: str = typer.Option(
        "", "--jira-project", envvar="MORNINGSTAR_JIRA_PROJECT_KEY"
    ),
    jira_label: str = typer.Option("morningstar", "--jira-label"),
    gh_repo: str = typer.Option("", "--gh-repo", envvar="MORNINGSTAR_GH_REPO"),
    base_branch: str = typer.Option("main", "--base-branch"),
    slack_webhook: str = typer.Option(
        "", "--slack-webhook", envvar="MORNINGSTAR_SLACK_WEBHOOK"
    ),
    slack_bot_token: str = typer.Option(
        "", "--slack-bot-token", envvar="MORNINGSTAR_SLACK_BOT_TOKEN"
    ),
    slack_channel: str = typer.Option(
        "", "--slack-channel", envvar="MORNINGSTAR_SLACK_CHANNEL_ID"
    ),
    question_timeout: int = typer.Option(300, "--question-timeout", min=30, max=1800),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Scan Notion DB + Jira for pending work items and process them.

    Designed for scheduled execution (cron / GitHub Actions). Each pending
    item is branched, implemented, committed, pushed, PR'd, and its source
    row flipped to Done/Failed.
    """
    print_banner(console)

    try:
        validate_model(model)
    except ValueError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1) from e

    if slack_webhook:
        try:
            validate_slack_webhook(slack_webhook)
        except ValueError as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            raise typer.Exit(1) from e
    if slack_bot_token:
        try:
            validate_bot_token(slack_bot_token)
        except ValueError as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            raise typer.Exit(1) from e

    if not (notion_db_id or jira_url):
        console.print(
            "[bold red]Error:[/bold red] Must configure at least one source: "
            "--notion-db-id or --jira-url (or env vars)."
        )
        raise typer.Exit(1)

    cfg = QueueConfig(
        repo_path=repo,
        model=model,
        per_run_budget=per_run_budget,
        per_task_budget=per_task_budget,
        weekly_budget=weekly_budget,
        max_tasks=max_tasks,
        notion_db_id=notion_db_id,
        notion_token=notion_token,
        jira_url=jira_url,
        jira_email=jira_email,
        jira_token=jira_token,
        jira_project_key=jira_project_key,
        jira_label=jira_label,
        gh_repo=gh_repo,
        base_branch=base_branch,
        slack_webhook=slack_webhook,
        slack_bot_token=slack_bot_token,
        slack_channel=slack_channel,
        question_timeout=question_timeout,
        dry_run=dry_run,
    )

    result = process_queue(cfg)

    summary = Table(title="Queue Run", border_style="bright_yellow", show_lines=True)
    summary.add_column("Metric", style="dim")
    summary.add_column("Value", style="bold")
    summary.add_row("Items scanned", str(result.scanned))
    summary.add_row("Processed", str(result.processed))
    summary.add_row("Succeeded", f"[green]{result.succeeded}[/green]")
    summary.add_row("Failed", f"[red]{result.failed}[/red]")
    summary.add_row("Skipped (dry-run)", str(result.skipped))
    summary.add_row("Run cost", f"[yellow]${result.total_cost:.2f}[/yellow]")
    summary.add_row("PRs opened", "\n".join(result.prs_opened) or "-")
    console.print(summary)

    if result.failed > 0 and result.succeeded == 0:
        raise typer.Exit(1)


_DURATION_RE = _re.compile(r"^\s*(\d+)\s*([smhd])\s*$", _re.IGNORECASE)


def _parse_duration(text: str) -> _dt.timedelta:
    """Parse '30s' / '10m' / '24h' / '7d' into a timedelta.

    Case-insensitive. Raises ValueError on malformed input.
    """
    match = _DURATION_RE.match(text)
    if not match:
        raise ValueError(
            f"Invalid duration {text!r}. Expected '<int><unit>' where unit is "
            "s, m, h, or d (e.g. '24h', '7d')."
        )
    n = int(match.group(1))
    unit = match.group(2).lower()
    if unit == "s":
        return _dt.timedelta(seconds=n)
    if unit == "m":
        return _dt.timedelta(minutes=n)
    if unit == "h":
        return _dt.timedelta(hours=n)
    return _dt.timedelta(days=n)


def _filter_since(records: list, since: str | None) -> list:
    """Keep records whose ISO timestamp >= now - duration. Bad timestamps are kept."""
    if not since:
        return records
    delta = _parse_duration(since)
    cutoff = _dt.datetime.now(_dt.timezone.utc) - delta
    kept = []
    for rec in records:
        try:
            ts = _dt.datetime.fromisoformat(rec.timestamp)
        except (ValueError, TypeError):
            kept.append(rec)
            continue
        if ts >= cutoff:
            kept.append(rec)
    return kept


@app.command()
def status(
    repo: Path = typer.Option(
        Path("."),
        "--repo",
        "-r",
        help="Target repository (the one MorningStar processes).",
        exists=True,
        dir_okay=True,
        file_okay=False,
        resolve_path=True,
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        "-n",
        min=1,
        max=100,
        help="Number of recent runs to display.",
    ),
    weekly_budget: float = typer.Option(
        200.0,
        "--weekly-budget",
        envvar="MORNINGSTAR_WEEKLY_BUDGET",
        min=0.01,
        help="Weekly budget for the spend bar (only used when no run history exists).",
    ),
    since: str = typer.Option(
        "",
        "--since",
        help="Only include runs newer than this duration (e.g. '24h', '7d').",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit a machine-readable JSON snapshot instead of a Rich dashboard.",
    ),
) -> None:
    """Show queue health: weekly spend, recent runs, last PRs opened."""
    week_key, spend_so_far = read_weekly_spend(repo)

    # `--since` filters first, `--limit` then trims the most recent N. Reading
    # all records is fine -- the file is capped at 500.
    all_history = read_run_history(repo)
    if since:
        try:
            all_history = _filter_since(all_history, since)
        except ValueError as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            raise typer.Exit(1) from e
    history = all_history[-limit:] if limit else all_history

    # Prefer the budget from the most recent run record so the bar reflects
    # what actually constrained the system, not the CLI default.
    budget = history[-1].weekly_budget if history else weekly_budget
    pct = min(100.0, (spend_so_far / budget) * 100.0) if budget > 0 else 0.0

    total_processed = sum(r.processed for r in history)
    total_succeeded = sum(r.succeeded for r in history)
    total_failed = sum(r.failed for r in history)
    total_cost = sum(r.total_cost for r in history)
    success_rate = (
        (total_succeeded / total_processed) * 100.0 if total_processed else 0.0
    )
    recent_prs = [pr for rec in reversed(history) for pr in rec.prs_opened][:10]

    if json_output:
        payload = {
            "week_key": week_key,
            "weekly_spend": round(spend_so_far, 4),
            "weekly_budget": round(budget, 4),
            "weekly_pct": round(pct, 2),
            "since": since or None,
            "limit": limit,
            "window": {
                "runs": len(history),
                "items_processed": total_processed,
                "items_succeeded": total_succeeded,
                "items_failed": total_failed,
                "success_rate_pct": round(success_rate, 2),
                "total_cost": round(total_cost, 4),
            },
            "recent_prs": recent_prs,
            "runs": [
                {
                    "timestamp": r.timestamp,
                    "week_key": r.week_key,
                    "scanned": r.scanned,
                    "processed": r.processed,
                    "succeeded": r.succeeded,
                    "failed": r.failed,
                    "skipped": r.skipped,
                    "total_cost": round(r.total_cost, 4),
                    "weekly_spend_after": round(r.weekly_spend_after, 4),
                    "weekly_budget": round(r.weekly_budget, 4),
                    "prs_opened": list(r.prs_opened),
                    "dry_run": r.dry_run,
                }
                for r in history
            ],
        }
        # print() (not console.print) keeps stdout pristine for piping into jq.
        print(_json.dumps(payload, indent=2))
        return

    print_banner(console)

    bar_width = 30
    filled = int(round(bar_width * pct / 100.0))
    bar = "█" * filled + "░" * (bar_width - filled)
    bar_color = "green" if pct < 60 else "yellow" if pct < 90 else "red"

    spend_panel = Panel.fit(
        f"[bold]Week[/bold] {week_key}\n"
        f"[{bar_color}]{bar}[/{bar_color}] {pct:5.1f}%\n"
        f"[bold]${spend_so_far:.2f}[/bold] / ${budget:.2f}"
        + (f"\n[dim]Window: --since {since}[/dim]" if since else ""),
        title="Weekly spend",
        border_style="bright_yellow",
    )
    console.print(spend_panel)

    if not history:
        if since:
            console.print(
                f"[dim]No runs in the last {since}. Try a wider window or "
                f"check `morningstar process-queue` is firing.[/dim]"
            )
        else:
            console.print(
                "[dim]No run history yet. "
                "Run [bold]morningstar process-queue[/bold] to start.[/dim]"
            )
        return

    runs_table = Table(
        title=f"Recent runs (last {len(history)})",
        border_style="bright_yellow",
        show_lines=False,
    )
    runs_table.add_column("Time (UTC)", style="dim", no_wrap=True)
    runs_table.add_column("Scanned", justify="right")
    runs_table.add_column("OK", justify="right", style="green")
    runs_table.add_column("Fail", justify="right", style="red")
    runs_table.add_column("Skip", justify="right", style="cyan")
    runs_table.add_column("Cost", justify="right", style="yellow")
    runs_table.add_column("Mode", justify="center")

    for rec in reversed(history):
        runs_table.add_row(
            rec.timestamp.replace("+00:00", "Z"),
            str(rec.scanned),
            str(rec.succeeded),
            str(rec.failed),
            str(rec.skipped),
            f"${rec.total_cost:.2f}",
            "dry" if rec.dry_run else "live",
        )
    console.print(runs_table)

    health_color = (
        "green" if success_rate >= 80 or total_processed == 0
        else "yellow" if success_rate >= 50
        else "red"
    )
    summary = Table(border_style="bright_blue", show_header=False)
    summary.add_column("Metric", style="dim")
    summary.add_column("Value", style="bold")
    summary.add_row("Window", f"{len(history)} run(s)")
    summary.add_row("Items processed", str(total_processed))
    summary.add_row(
        "Success rate", f"[{health_color}]{success_rate:.1f}%[/{health_color}]"
    )
    summary.add_row("Items failed", f"[red]{total_failed}[/red]")
    summary.add_row("Total cost (window)", f"${total_cost:.2f}")
    console.print(summary)

    if recent_prs:
        prs_table = Table(
            title="Recent PRs (most recent first)",
            border_style="bright_green",
            show_header=False,
        )
        prs_table.add_column("URL", style="cyan")
        for pr in recent_prs:
            prs_table.add_row(pr)
        console.print(prs_table)


def main() -> None:
    app()
