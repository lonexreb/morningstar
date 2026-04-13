"""MorningStar CLI -- the main entry point."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from morningstar import __version__
from morningstar.banner import print_banner
from morningstar.engine import (
    RunState,
    execute_task,
    fetch_prd,
    generate_tasks,
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
        raise typer.Exit(1)

    try:
        validate_slack_webhook(slack_webhook)
    except ValueError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    if slack_bot_token:
        try:
            validate_bot_token(slack_bot_token)
        except ValueError as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            raise typer.Exit(1)
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
            raise typer.Exit(1)

    console.print(f"  [green]PRD fetched[/green] ({prd_text.count(chr(10)) + 1} lines, ${prd_cost:.2f})")

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
            raise typer.Exit(1)

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
        slack_post(slack_webhook, f"MorningStar dry run: {task_count} tasks identified. Cost: ${state.cost:.2f}")
        raise typer.Exit(0)

    # ── Confirmation gate ─────────────────────────────────────────
    if not yes:
        console.print(
            Panel(
                f"MorningStar will execute [bold]{task_count} tasks[/bold] in [cyan]{repo}[/cyan]\n"
                f"using Claude Code with [bold red]shell access and no human confirmation[/bold red].\n\n"
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
                slack_post(slack_webhook, f"Budget limit (${state.cost:.2f}/${budget:.2f}). Stopping.")
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
                slack_post(slack_webhook, f"[{i + 1}/{task_count}] Completed: *{title}* (${result.cost:.2f})")
            else:
                state.failed += 1
                slack_post(slack_webhook, f"[{i + 1}/{task_count}] Failed: *{title}* (${result.cost:.2f})")

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


def main() -> None:
    app()
