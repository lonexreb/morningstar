# MorningStar User Guide

## What is MorningStar?

MorningStar is a CLI tool that reads a product requirements document (PRD) from Notion and autonomously implements it in your codebase. It:

- Fetches the PRD from a Notion page
- Analyzes your codebase to find what's missing
- Generates a task list of concrete work items
- Implements each task using Claude Code
- Writes tests, runs them, and fixes failures
- Commits each completed task to git
- Posts progress updates to Slack

You point it at a PRD and a repo. It codes until the PRD is fulfilled.

MorningStar ships in two forms:

- **Claude Code plugin** (recommended) -- use `/morningstar:run` inside any Claude Code session.
- **Standalone CLI** -- `morningstar run ...` from your shell, installed via `pipx`.

Both wrap the same engine. Pick whichever fits your workflow.

---

## Quick Start (Claude Code Plugin)

The fastest path. Skip this section if you prefer the standalone CLI.

### 1. Install the plugin

Inside Claude Code, register MorningStar's marketplace and install:

```
/plugin marketplace add lonexreb/morningstar
/plugin install morningstar@morningstar
```

Or, in one shot, install directly from the GitHub source:

```
/plugin install morningstar@https://github.com/lonexreb/morningstar
```

Both paths resolve to the same plugin manifest (`.claude-plugin/plugin.json`). The marketplace path is preferred -- it lets you receive updates with `/plugin marketplace update morningstar`.

### 2. Connect Notion MCP

Claude Code must have a Notion MCP connection so the plugin can read your PRD:

```bash
claude mcp list
```

If Notion is missing, follow [Claude Code MCP docs](https://code.claude.com/docs/en/mcp).

### 3. (Optional) Configure Slack

Set these environment variables before launching Claude Code if you want progress updates and two-way Q&A:

```bash
export MORNINGSTAR_SLACK_WEBHOOK="https://hooks.slack.com/services/..."
export MORNINGSTAR_SLACK_BOT_TOKEN="xoxb-..."        # two-way Q&A only
export MORNINGSTAR_SLACK_CHANNEL_ID="C01234567"      # two-way Q&A only
```

### 4. Run

| Command | What it does |
|---------|--------------|
| `/morningstar:run <notion-url>` | Full autonomous run (fetch PRD -> plan -> execute with commits) |
| `/morningstar:dry-run <notion-url>` | Preview the task plan only, no code changes |
| `/morningstar:version` | Show plugin version |

Example:

```
/morningstar:run https://notion.so/My-PRD-abc123 --model sonnet --budget 50
```

The plugin delegates to the `morningstar-runner` agent, which follows the same 4-phase workflow as the CLI (fetch -> plan -> execute -> summarize).

---

## Prerequisites (Standalone CLI)

Skip this section if you're using the plugin path above.

Before using MorningStar from the shell, you need:

### 1. Python 3.10+

```bash
python3 --version  # Must be 3.10 or higher
```

### 2. Claude Code CLI

Install and authenticate:

```bash
# Install Claude Code
npm install -g @anthropic-ai/claude-code

# Authenticate
claude auth login
```

Verify it works:

```bash
claude -p "Hello" --output-format json
```

### 3. Notion MCP Connection

MorningStar uses Claude Code's MCP (Model Context Protocol) to read Notion pages. This needs to be configured in your Claude Code settings.

Check if Notion MCP is already connected:

```bash
claude mcp list
```

If not connected, follow the [Claude Code MCP docs](https://code.claude.com/docs/en/mcp) to add the Notion integration.

### 4. Slack Incoming Webhook

Create a Slack webhook for your channel:

1. Go to [Slack API: Incoming Webhooks](https://api.slack.com/messaging/webhooks)
2. Create a new webhook for your workspace
3. Select the channel for agent updates
4. Copy the webhook URL (starts with `https://hooks.slack.com/services/...`)

### 5. Anthropic API Key

Set your API key as an environment variable:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

---

## Installation

### From PyPI (recommended)

```bash
pipx install morningstar-agent
```

### From Source

```bash
git clone https://github.com/lonexreb/morningstar.git
cd morningstar
pip install -e .
```

### Verify Installation

```bash
morningstar version
# Output: morningstar 0.1.0
```

---

## Quick Start

### Step 1: Prepare Your Notion PRD

Create a Notion page with your product requirements. Include:
- Feature descriptions
- Acceptance criteria
- Technical constraints

Copy the page URL or ID. Both formats work:
- Full URL: `https://www.notion.so/My-PRD-337e989c4bac807982f8ec02208efe8d`
- Just the ID: `337e989c4bac807982f8ec02208efe8d`

### Step 2: Set Up Slack Webhook

Store the webhook URL as an environment variable (recommended over CLI flag to keep it out of shell history):

```bash
export MORNINGSTAR_SLACK_WEBHOOK="https://hooks.slack.com/services/T.../B.../xxx"
```

### Step 3: Preview with Dry Run

Before letting the agent code, preview what it plans to do:

```bash
morningstar run \
  --notion-url "337e989c4bac807982f8ec02208efe8d" \
  --repo /path/to/your/project \
  --dry-run
```

This will:
1. Fetch the PRD from Notion
2. Analyze your codebase
3. Generate a task list
4. Display the task plan and exit (no code changes)

### Step 4: Run for Real

Once you're satisfied with the task plan:

```bash
morningstar run \
  --notion-url "337e989c4bac807982f8ec02208efe8d" \
  --repo /path/to/your/project
```

MorningStar will show the task plan and ask for confirmation before executing:

```
+-----------------------------------------------------------+
| Confirm Execution                                         |
|                                                           |
| MorningStar will execute 7 tasks in /path/to/project      |
| using Claude Code with shell access and no human          |
| confirmation.                                             |
|                                                           |
| Budget: $50.00 total, $5.00 per task.                     |
+-----------------------------------------------------------+
Proceed? [y/N]:
```

Type `y` to start. The agent will work through each task, committing and posting to Slack as it goes.

### Step 5: Review Results

After completion, you'll see a summary:

```
+-----------------------+
| Run Complete          |
|-----------------------|
| Tasks completed | 6   |
| Tasks failed    | 1   |
| Total cost      | $18 |
| Budget          | $50 |
| Logs            | ... |
+-----------------------+
```

Review the git log for the agent's commits:

```bash
cd /path/to/your/project
git log --oneline -10
```

Check `.agent-logs/` for detailed output from each task.

---

## CLI Reference

### `morningstar run`

The main command. Fetches PRD, generates tasks, and executes them.

```bash
morningstar run [OPTIONS]
```

#### Required Options

| Flag | Short | Description |
|------|-------|-------------|
| `--notion-url` | `-n` | Notion page URL or ID containing the PRD |
| `--repo` | `-r` | Path to the target repository (must exist) |

#### Credential Options

| Flag | Short | Env Var | Description |
|------|-------|---------|-------------|
| `--slack-webhook` | `-s` | `MORNINGSTAR_SLACK_WEBHOOK` | Slack incoming webhook URL |
| `--slack-bot-token` | | `MORNINGSTAR_SLACK_BOT_TOKEN` | Bot token (`xoxb-...`) for two-way Q&A |
| `--slack-channel` | | `MORNINGSTAR_SLACK_CHANNEL` | Channel ID for posting questions |

Using environment variables is recommended to avoid exposing secrets in shell history and process listings.

#### Configuration Options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--model` | `-m` | `sonnet` | Claude model to use |
| `--budget` | `-b` | `50.00` | Total USD budget for the entire run |
| `--task-budget` | | `5.00` | Maximum USD per individual task |
| `--max-tasks` | | `20` | Maximum number of tasks to generate (1-100) |
| `--question-timeout` | | `300` | Seconds to wait for Slack answer (30-1800) |

#### Control Options

| Flag | Short | Description |
|------|-------|-------------|
| `--dry-run` | | Fetch PRD and generate tasks, but do not execute |
| `--yes` | `-y` | Skip the confirmation prompt |

### `morningstar version`

Prints the version number.

```bash
morningstar version
# morningstar 0.1.0
```

### `morningstar status`

Show queue health for a repo MorningStar processes — weekly spend bar, recent runs, aggregate success rate, and last PR URLs. Reads `.morningstar/run-history.jsonl` written by every queue run; works offline.

```bash
morningstar status --repo /path/to/repo
morningstar status --repo /path/to/repo --limit 25
morningstar status --repo /path/to/repo --since 24h           # only the last day
morningstar status --repo /path/to/repo --json | jq           # script-friendly
```

| Option | Default | Notes |
|--------|---------|-------|
| `--repo`, `-r` | `.` | Target repo (the one `process-queue` runs against). |
| `--limit`, `-n` | `10` | How many recent runs to show. Range: 1–100. |
| `--since` | _none_ | Filter to runs newer than this duration. Accepts `<int><unit>` where unit is `s`, `m`, `h`, or `d` (case-insensitive). Examples: `30m`, `24h`, `7d`. |
| `--json` | _off_ | Emit a machine-readable JSON snapshot to stdout instead of the Rich dashboard. Banner is suppressed so output is pipe-safe (`jq`, etc.). |
| `--weekly-budget` | `200.0` | Only used as a fallback when no run history exists yet. Once history is present, the budget from the most recent run is shown. |

**What you see (default Rich mode):**

- **Weekly spend** — color-coded bar (green < 60% / yellow < 90% / red ≥ 90%) showing `spend / budget` for the current ISO week.
- **Recent runs** — table with timestamp, items scanned, succeeded, failed, skipped (dry-run), cost, and live/dry mode.
- **Aggregate health** — total processed, success rate (color-coded ≥ 80% green / ≥ 50% yellow / else red), failed count, total spend across the displayed window.
- **Recent PRs** — most recent 10 PR URLs across the displayed runs.

**JSON shape (`--json`):**

```jsonc
{
  "week_key": "2026-W18",
  "weekly_spend": 12.50,
  "weekly_budget": 200.00,
  "weekly_pct": 6.25,
  "since": "24h",                  // null if --since was not used
  "limit": 10,
  "window": {
    "runs": 3,
    "items_processed": 5,
    "items_succeeded": 4,
    "items_failed": 1,
    "success_rate_pct": 80.00,
    "total_cost": 7.25
  },
  "recent_prs": ["https://github.com/.../pull/123"],
  "runs": [ /* RunRecord per run, oldest-first */ ]
}
```

Useful for cron-driven monitoring (post a Slack alert when `success_rate_pct < 50`, when `weekly_pct > 90`, etc.).

**Empty history**: if no runs have been recorded yet, the command prints a hint to run `morningstar process-queue` first instead of erroring. With `--since`, an empty window prints a "no runs in the last X" message.

---

## Model Selection

MorningStar supports these Claude models:

| Model | Best For | Cost |
|-------|---------|------|
| `sonnet` (default) | General coding tasks, good balance of speed and quality | $$ |
| `opus` | Complex architectural changes, multi-file refactors | $$$$ |
| `haiku` | Simple tasks, quick fixes, test writing | $ |

Full model IDs are also accepted: `claude-sonnet-4-6`, `claude-opus-4-6`, `claude-haiku-4-5`, `claude-sonnet-4-5`, `claude-opus-4-5`.

**Recommendation**: Start with `sonnet` (the default). Use `opus` if tasks are failing due to complexity. Use `haiku` for cost-sensitive runs with simple tasks.

---

## Budget Control

MorningStar tracks costs at every phase:

| Phase | Default Budget | Description |
|-------|---------------|-------------|
| PRD fetch | $1.00 (fixed) | Reading the Notion page |
| Task generation | $3.00 (fixed) | Analyzing codebase + generating task list |
| Per task | $5.00 (configurable via `--task-budget`) | Implementing each task |
| Retry | $3.00 (fixed) | Retrying a failed task |

The `--budget` flag sets the **total** cap across all phases. If the running total reaches the budget, MorningStar stops and reports what was completed.

### Examples

```bash
# Conservative: $20 total, $3 per task
morningstar run -n "..." -r /repo --budget 20 --task-budget 3

# Generous: $100 total, $10 per task (for complex tasks)
morningstar run -n "..." -r /repo --budget 100 --task-budget 10 --model opus
```

---

## Slack Integration

MorningStar posts updates at every step:

```
MorningStar started. Reading PRD from Notion...
PRD loaded. Analyzing codebase...
Found 7 tasks. Starting execution...
[1/7] Starting: Implement attendance analytics service
[1/7] Completed: Implement attendance analytics service ($1.80)
[2/7] Starting: Add homework analytics endpoints
[2/7] Completed: Add homework analytics endpoints ($1.50)
[3/7] Starting: Write analytics unit tests
[3/7] Failed: Write analytics unit tests ($2.10)
...
MorningStar complete: 6 done, 1 failed. Cost: $18.50/$50.00
```

### Setup

**Option A: Environment variable (recommended)**

```bash
export MORNINGSTAR_SLACK_WEBHOOK="https://hooks.slack.com/services/T.../B.../xxx"
morningstar run -n "..." -r /repo
```

**Option B: CLI flag**

```bash
morningstar run -n "..." -r /repo -s "https://hooks.slack.com/services/T.../B.../xxx"
```

The environment variable approach keeps the webhook URL out of your shell history and process listings.

### Two-Way Slack (Q&A)

If the agent needs a decision during task execution, it can ask a question in Slack and wait for your answer.

**Setup:**

1. Create a Slack App at [api.slack.com/apps](https://api.slack.com/apps)
2. Add Bot Token Scopes: `chat:write`, `channels:history`, `groups:history`
3. Install the app to your workspace
4. Copy the Bot User OAuth Token (`xoxb-...`)
5. Find your channel ID (right-click channel > "View channel details" > ID at bottom)

```bash
export MORNINGSTAR_SLACK_BOT_TOKEN="xoxb-..."
export MORNINGSTAR_SLACK_CHANNEL="C0A2DMV8JNB"
morningstar run -n "..." -r /repo
```

**How it works:**

1. During task execution, Claude outputs a `QUESTION:` block when it needs input
2. MorningStar posts the question to your Slack channel
3. It polls for a reply every 30 seconds (up to `--question-timeout`, default 5 min)
4. When you reply in the thread, the agent reads your answer and continues
5. If you don't reply in time, it proceeds with the default action

**Example Slack thread:**

```
Bot: "Implement auth module" needs input:
  > Should the API use JWT or session-based auth?
  Context: Both are supported by the framework.
  Default (if no reply in 5min): JWT

You: Use JWT with refresh tokens

Bot: [continues implementation with JWT + refresh tokens]
```

**Without bot token**: Questions are still posted to the webhook for visibility, but the agent proceeds immediately with the default -- no waiting.

---

## Notion Setup

### Supported Page Formats

MorningStar accepts either:

- **Full URL**: `https://www.notion.so/workspace/My-PRD-337e989c4bac807982f8ec02208efe8d`
- **Page ID**: `337e989c4bac807982f8ec02208efe8d`

### Writing Effective PRDs

MorningStar generates better tasks when the PRD includes:

1. **Clear feature descriptions** -- what the feature does, not just a name
2. **Acceptance criteria** -- how to verify each feature works
3. **Technical constraints** -- tech stack, libraries to use/avoid, conventions
4. **Data model** -- entity names, relationships, field types
5. **User roles** -- who can do what
6. **Edge cases** -- what to handle when things go wrong

MorningStar will also read your repo's `CLAUDE.md` and `README.md` for project conventions.

### What MorningStar Reads

The agent reads the **entire Notion page** including:
- Headings and body text
- Tables
- Bullet lists
- Code blocks
- Nested content

It does NOT follow links to other pages -- put everything the agent needs in a single page.

---

## Logs and Debugging

### Log Location

All logs are saved to `<your-repo>/.agent-logs/`:

```
.agent-logs/
  prd.md               -- Full PRD text fetched from Notion
  tasks.json           -- Generated task list
  task-analytics-svc.json     -- Claude's output for task "analytics-svc"
  task-analytics-svc-retry.json -- Retry output (if first attempt failed)
  task-attendance-chart.json   -- Claude's output for task "attendance-chart"
  ...
```

### Reading Task Logs

Each `task-*.json` file contains Claude's full response:

```bash
cat .agent-logs/task-analytics-svc.json | jq '.result' | head -50
```

Key fields:
- `result` -- Claude's text output (what it did)
- `is_error` -- whether it failed
- `total_cost_usd` -- how much it cost
- `session_id` -- for manual session resumption

### Cleaning Up Logs

Logs are gitignored by default. To clean up:

```bash
rm -rf /path/to/repo/.agent-logs/
```

---

## Troubleshooting

### "Failed to fetch PRD from Notion"

**Cause**: Claude Code can't read the Notion page.

**Fix**:
1. Verify Notion MCP is connected: `claude mcp list`
2. Verify the page is accessible (not private/restricted)
3. Check `.agent-logs/prd-error.json` for the detailed error
4. Try fetching manually: `claude -p "Read this Notion page: <url>"`

### "Failed to generate task list"

**Cause**: Claude couldn't analyze the codebase or produce valid JSON.

**Fix**:
1. Check `.agent-logs/tasks-error.json` for the raw response
2. Ensure the repo has a `README.md` or `CLAUDE.md` with project context
3. Try with a simpler PRD (fewer features)
4. Try with `--model opus` for more reasoning power

### "Invalid model" error

**Cause**: Model name not in the allowlist.

**Fix**: Use one of: `sonnet`, `opus`, `haiku`, `claude-sonnet-4-6`, `claude-opus-4-6`, `claude-haiku-4-5`, `claude-sonnet-4-5`, `claude-opus-4-5`.

### "Slack webhook must be a valid URL"

**Cause**: The webhook URL doesn't match the expected Slack format.

**Fix**: The URL must start with `https://hooks.slack.com/services/` followed by three path segments. Get a new webhook from [Slack API](https://api.slack.com/messaging/webhooks).

### Tasks keep failing

**Possible causes**:
1. **PRD too vague** -- add more detail, acceptance criteria, and technical context
2. **Codebase too complex** -- add a `CLAUDE.md` file explaining project structure and conventions
3. **Budget too low** -- increase `--task-budget` for complex tasks
4. **Wrong model** -- try `--model opus` for complex tasks

### Budget exceeded before finishing

**Fix**: Increase `--budget` or reduce `--max-tasks` to focus on fewer, higher-priority items. You can also re-run with `--dry-run` first to estimate how many tasks will be generated.

---

## Tips

### Add a CLAUDE.md to Your Repo

MorningStar instructs Claude to read `CLAUDE.md` first. This file should contain:
- Project structure overview
- Tech stack and key dependencies
- Coding conventions (naming, formatting, patterns)
- How to run tests
- How to run the dev server
- Any gotchas or non-obvious patterns

The better your `CLAUDE.md`, the better MorningStar's output.

### Use Dry Run First

Always preview before executing:

```bash
morningstar run -n "..." -r /repo --dry-run
```

This costs ~$1-4 for PRD fetch + task generation, but saves you from a $50 run that does the wrong thing.

### Work on a Branch

Run MorningStar on a feature branch so you can review before merging:

```bash
cd /path/to/repo
git checkout -b morningstar/analytics
morningstar run -n "..." -r .
# Review commits, then merge if happy
```

### Iterate with Smaller PRDs

Instead of one massive PRD, break your requirements into focused pages:
- "Analytics Dashboard" -- one MorningStar run
- "Payment Integration" -- another run
- "Email Notifications" -- another run

Smaller, focused PRDs produce better results than kitchen-sink documents.

---

## Demo Walkthrough (No Credentials)

Before configuring Notion, Jira, or Slack, you can drive the queue processor end-to-end against a temporary git repository with every external integration mocked. The demo lives at the repo root:

```bash
python morningstar_demo.py
```

What it does:

- Creates a throwaway git repo in a temp directory
- Mocks `fetch_pending_notion`, `fetch_pending_jira`, `set_notion_status`, `fetch_prd`, `generate_tasks`, `execute_task`, and `open_github_pr`
- Drives a fake "Add hello world endpoint" PRD through the full state machine
- Writes real files (`app.py`, `test_app.py`) and commits them with the standard `morningstar(<task-id>): <title>` message
- Prints a narrated summary -- items scanned, success/failure counts, simulated cost, weekly spend ledger, PR URL
- Cleans up the temp directory on exit

Use it to sanity-check the engine after pulling new changes, validate a fresh install, or walk a stakeholder through the pipeline live without provisioning credentials.

---

## 24/7 Setup (Scheduled Queue Processor)

MorningStar can run continuously, polling a Notion database and Jira project every 15 minutes, processing any PRDs it finds, and opening PRs against a target repo. This is the path for handoff to an operations team.

### Architecture (summary)

Two cooperating layers:

1. **Executor** -- `.github/workflows/morningstar-scheduled.yml`. Cron every 15 minutes. Runs `morningstar process-queue`, which is the heavy lifter: clone target repo, fetch PRD, plan, implement, push, PR.
2. **Watcher** -- `/morningstar:watch` skill on Claude Cloud Tasks (hourly). Does a lightweight scan and dispatches the executor. Defense in depth; not required if the GH cron suffices.

### Notion database schema

Create a Notion database with at minimum:

| Column | Type | Values |
|---|---|---|
| *Title* (e.g. `Name`) | Title | -- |
| `Status` | Select | `Pending`, `Running`, `Done`, `Failed` |
| `PR` | URL | Populated by MorningStar |
| `Notes` | Rich text | Populated by MorningStar |
| `Notion URL` or `PRD URL` (optional) | URL | If set, overrides the row URL as PRD source |

Share the DB with your Notion integration (the one whose token you use).

### Jira setup

- Tickets with label `morningstar` in status `To Do` are picked up.
- If the ticket description contains a Notion URL, that URL is used as the PRD.
- Otherwise, the description body is used inline.
- MorningStar transitions: `To Do` → `In Progress` (start) → `Done` / `Failed` (finish).

### GitHub repository configuration

In the repo where the `morningstar-scheduled.yml` workflow lives:

**Variables** (Settings → Secrets and variables → Actions → Variables):

- `MORNINGSTAR_ENV` -- e.g. `prod` or `dev` (picks which environment's secrets apply)
- `MORNINGSTAR_NOTION_DB_ID`
- `MORNINGSTAR_JIRA_URL`
- `MORNINGSTAR_JIRA_PROJECT_KEY`
- `MORNINGSTAR_WEEKLY_BUDGET` -- USD cap per ISO week
- `MORNINGSTAR_TARGET_REPO` -- `owner/name` of the repo to modify (optional; if empty the workflow modifies its own repo)
- `MORNINGSTAR_TARGET_BRANCH` -- default `main`

**Secrets** (same path, on the environment you named in `MORNINGSTAR_ENV`):

- `ANTHROPIC_API_KEY`
- `MORNINGSTAR_NOTION_TOKEN`
- `MORNINGSTAR_JIRA_EMAIL`, `MORNINGSTAR_JIRA_TOKEN`
- `MORNINGSTAR_SLACK_WEBHOOK`
- `MORNINGSTAR_SLACK_BOT_TOKEN` (optional, for two-way Q&A)
- `MORNINGSTAR_SLACK_CHANNEL_ID` (optional, for two-way Q&A)
- `MORNINGSTAR_TARGET_REPO_TOKEN` -- PAT with `repo` + `workflow` scopes on the target repo

### Verify the setup

**Dry-run workflow (manual):**

GitHub UI → Actions → `morningstar-scheduled-dryrun` → Run workflow. This scans the queue and reports counts without executing. Use this first to confirm credentials are wired correctly.

**Real run (manual):**

GitHub UI → Actions → `morningstar-scheduled` → Run workflow.

**Cron:** The workflow fires every 15 minutes. First scheduled fire happens within ~15 min of merging the workflow file to the default branch.

### Running the CLI directly (for debugging)

Locally, with the same env vars exported:

```bash
morningstar process-queue --dry-run   # preview only
morningstar process-queue             # full execution
```

Flags:

| Flag | Env var | Default | Purpose |
|---|---|---|---|
| `--repo` | -- | `.` | Target repo path |
| `--notion-db-id` | `MORNINGSTAR_NOTION_DB_ID` | -- | |
| `--notion-token` | `MORNINGSTAR_NOTION_TOKEN` | -- | |
| `--jira-url` | `MORNINGSTAR_JIRA_URL` | -- | |
| `--jira-email` | `MORNINGSTAR_JIRA_EMAIL` | -- | |
| `--jira-token` | `MORNINGSTAR_JIRA_TOKEN` | -- | |
| `--jira-project` | `MORNINGSTAR_JIRA_PROJECT_KEY` | -- | |
| `--weekly-budget` | `MORNINGSTAR_WEEKLY_BUDGET` | 200 | USD/ISO-week |
| `--run-budget` | -- | 25 | USD/run |
| `--task-budget` | -- | 5 | USD/task |
| `--gh-repo` | `MORNINGSTAR_GH_REPO` | -- | `owner/name` for PR target |
| `--base-branch` | -- | `main` | PR base |

### Register the watcher (optional)

In a Claude Code session:

```
/schedule /morningstar:watch --cron "0 * * * *"
```

Note: Anthropic Cloud Tasks auto-expire after 7 days. Re-register weekly, or skip the watcher and rely on the 15-minute GH Actions cron.

### See also

For the full day-to-day ops runbook (pause, secret rotation, stuck-item recovery, failure modes), see [HANDOVER.md](../HANDOVER.md).
