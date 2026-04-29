---
description: Shows MorningStar queue health for a repo -- weekly spend bar, recent runs, success rate, and most recent PR URLs. Use when the user asks any of "morningstar status", "queue health", "how is morningstar doing", "what did morningstar ship this week", "weekly spend so far", "morningstar dashboard", "show recent runs", "is the agent healthy". Read-only -- no Notion / Jira / Slack calls; works offline against the local repo.
argument-hint: [--repo /path/to/repo] [--limit 10]
---

# MorningStar Status

Display a quick health dashboard for the 24/7 MorningStar queue running against a repo. This skill is the user-facing command equivalent of `morningstar status`.

## Arguments

User provided: $ARGUMENTS

Optional:
- **--repo** (default: current working directory): path to the target repo MorningStar processes (the one with `.morningstar/run-history.jsonl` written to it).
- **--limit** (default: `10`): number of recent runs to render. Range: 1–100.

## Instructions

1. **Pick the repo**: parse `--repo` from `$ARGUMENTS`, default to `.` if absent.

2. **Run** the CLI:
   ```bash
   morningstar status --repo <repo> --limit <limit>
   ```
   This is the only call needed -- the CLI does all rendering. If the user does not have `morningstar` on `$PATH` (rare, but happens with non-pipx installs), fall back to:
   ```bash
   python -m morningstar.cli status --repo <repo> --limit <limit>
   ```

3. **Pass through the output verbatim** (it's a Rich-rendered dashboard with the spend bar, runs table, aggregate health, and PR list).

4. **If the dashboard says "No run history yet"**, suggest the user run `morningstar process-queue` (or wait for the next scheduled tick) and exit cleanly. Don't attempt to fabricate fake history.

5. **Health interpretation hint** (only mention if the user asks "is it healthy?"):
   - Green success rate ≥ 80% → healthy
   - Yellow 50–80% → watch closely; check `.agent-logs/`
   - Red < 50% → likely model/budget/PRD problem; open the latest failed run's `task-<id>.json` for the Claude transcript

## Why this exists

Operators of the 24/7 system needed a fast way to check on the agent without opening GitHub Actions, Notion, and Slack in three tabs. `morningstar status` reads `.morningstar/run-history.jsonl` (auto-written by every queue run, capped at 500 records) and prints a full snapshot in one command. No external API calls; no credentials needed.

## Example

```
/morningstar:status --repo /Users/me/projects/customer-portal --limit 20
```
