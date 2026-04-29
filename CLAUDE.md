# MorningStar

Autonomous coding agent that reads a PRD from Notion, analyzes a codebase, generates tasks, and implements them using Claude Code CLI. Posts progress to Slack.

## Tech Stack

- Python 3.10+ with `typer` + `rich`
- Claude Code CLI (headless mode via `-p`)
- Notion MCP for PRD ingestion
- Slack webhooks for status updates + bot token for two-way Q&A

## Install

```bash
pip install -e ".[dev]"
```

## Usage

```bash
morningstar run \
  --notion-url "https://notion.so/PRD-abc123" \
  --slack-webhook "https://hooks.slack.com/services/..." \
  --repo /path/to/repo
```

## Project Structure

```
src/morningstar/
  __init__.py    -- version
  cli.py         -- typer CLI entry point (run, version, dry-run, process-queue, status)
  engine.py      -- core loop + 24/7 queue processor (fetch, plan, execute, commit, PR) + RunRecord history
  banner.py      -- ASCII art banner and branding

morningstar_demo.py  -- standalone walkthrough of process-queue with all I/O mocked
.github/workflows/   -- 15-min cron executor + manual dry-run executor
.claude-plugin/
  plugin.json        -- plugin manifest (name, version, keywords, paths)
  marketplace.json   -- self-hosted marketplace entry (category, tags, source)
agents/morningstar-runner.md  -- autonomous orchestrator agent
skills/run|dry-run|version|watch  -- user-facing slash commands
```

## Conventions

- `TaskResult` and `RunRecord` are frozen (immutable). `RunState` and `QueueResult` are mutable (accumulated in the loop).
- All Claude CLI calls go through `_run_claude()` in engine.py
- One-way Slack posts go through `slack_post()` (webhook)
- Two-way Slack Q&A goes through `slack_post_and_get_reply()` (bot token + polling)
- Question detection via `parse_question_block()` regex on Claude output
- Logs written to `<target-repo>/.agent-logs/`
- Run history written to `<target-repo>/.morningstar/run-history.jsonl` (append-only, capped at 500 records). Surfaced by `morningstar status`.
- Weekly spend ledger lives at `<target-repo>/.morningstar/weekly-spend.json` (ISO week key + running total).
- Budget tracked via `RunState.cost` -- includes PRD fetch + task gen + execution
- All user-supplied inputs are validated before use (model allowlist, webhook URL, task IDs)
- AI-generated task IDs are sanitized via `_sanitize_task_id()` before filesystem use
- `git add` excludes sensitive file patterns (`.env`, `*.pem`, `*.key`, etc.)
- PRD fetch runs in a temp directory with read-only tools (no Bash)
- Task generation uses read-only tools (no Bash) -- only execution gets write + Bash

## Dev Commands

```bash
ruff check src/ tests/        # lint (clean)
mypy src/morningstar/         # type check (clean)
pytest                        # 152 tests, all passing
python morningstar_demo.py    # zero-credentials pipeline walkthrough
```

## Quality Bar

Before any commit:
- `ruff check src/ tests/` must pass
- `mypy src/morningstar/` must pass
- `pytest` must be green

`pyproject.toml` ignores B008 globally (typer.Option-in-defaults is idiomatic) and B017 in tests (frozen-dataclass mutation assertion).

## Discoverability (keep in sync)

When something user-facing changes, update *all* of these so MorningStar stays findable:

- `.claude-plugin/plugin.json` -- description + keywords (Claude Code marketplace + skill router)
- `.claude-plugin/marketplace.json` -- description + tags + category (self-hosted marketplace)
- `skills/*/SKILL.md` frontmatter `description` -- third-person, pushy, with explicit trigger phrases (Anthropic skill discovery best practice)
- `agents/morningstar-runner.md` frontmatter `description` -- with `PROACTIVELY` marker
- `README.md` -- badges, opening paragraph, Use Cases, FAQ (long-tail SEO)
- GitHub repo topics + description (set via `gh api -X PUT /repos/lonexreb/morningstar/topics ...`)
- `pyproject.toml` `keywords` (PyPI discovery)

The last source of truth is the GitHub topics list -- if the README mentions a capability that isn't a topic, add the topic.
