```
            .
           /|\
          / | \
         /  |  \
    ----'   |   '----
     \      |      /
      \     |     /
       \    |    /
        \   |   /
         \  |  /
          \ | /
           \|/
            '

 __  __  ___  ___ _  _ ___ _  _  ___ ___ _____ _   ___
|  \/  |/ _ \| _ \ \| |_ _| \| |/ __/ __|_   _/_\ | _ \
| |\/| | (_) |   / .` || || .` | (_ \__ \ | |/ _ \|   /
|_|  |_|\___/|_|_\_|\_|___|_|\_|\___|___/ |_/_/ \_\_|_\
```

**Autonomous coding agent that turns Notion PRDs into working code.**

Give it a PRD, a repo, and a Slack webhook. It reads the requirements, analyzes the codebase, figures out what's missing, and builds it -- task by task, with tests, commits, and progress updates.

---

## Install

### As Claude Code Plugin (recommended)

```bash
/plugin install morningstar@https://github.com/lonexreb/morningstar
```

Then use inside any Claude Code session:

```
/morningstar:run https://notion.so/Your-PRD-abc123
/morningstar:dry-run https://notion.so/Your-PRD-abc123
```

### As Standalone CLI

```bash
pipx install morningstar-agent
```

```bash
morningstar run \
  --notion-url "https://notion.so/Your-PRD-Page-abc123" \
  --slack-webhook "https://hooks.slack.com/services/T.../B.../xxx" \
  --repo /path/to/your/project
```

Or use environment variables for secrets:

```bash
export MORNINGSTAR_SLACK_WEBHOOK="https://hooks.slack.com/services/..."
morningstar run -n "notion-page-id" -r /path/to/repo
```

### Prerequisites

- [Claude Code CLI](https://claude.ai/code) installed and authenticated
- Notion MCP connected in your Claude Code config
- Python 3.10+ (for standalone CLI only)

### Options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--notion-url` | `-n` | required | Notion page URL or ID with the PRD |
| `--slack-webhook` | `-s` | env var | Slack webhook (or set `MORNINGSTAR_SLACK_WEBHOOK`) |
| `--repo` | `-r` | required | Path to the target repository |
| `--model` | `-m` | `sonnet` | Claude model (`sonnet`, `opus`, `haiku`) |
| `--budget` | `-b` | `50.00` | Total USD budget for the run |
| `--task-budget` | | `5.00` | Max USD per individual task |
| `--max-tasks` | | `20` | Maximum tasks to generate |
| `--dry-run` | | `false` | Fetch PRD + generate tasks without executing |
| `--yes` | `-y` | `false` | Skip confirmation prompt |
| `--slack-bot-token` | | env var | Bot token for two-way Slack Q&A (`MORNINGSTAR_SLACK_BOT_TOKEN`) |
| `--slack-channel` | | env var | Channel ID for questions (`MORNINGSTAR_SLACK_CHANNEL`) |
| `--question-timeout` | | `300` | Seconds to wait for Slack answer (30-1800) |

---

## How It Works

```
 1. Fetch PRD          Read full Notion page via Claude Code + MCP
                        |
 2. Analyze             Explore the codebase, diff against PRD requirements
                        |
 3. Plan                Generate a structured task list (ordered by dependency)
                        |
 4. Confirm             Show task plan, ask for human confirmation
                        |
 5. Execute             For each task:
                          - Implement code changes
                          - Write/update tests
                          - Run tests, fix failures
                          - If stuck, ask question in Slack and wait for answer
                          - Git commit
                          - Post to Slack
                        |
 6. Summary             Report: tasks done, tasks failed, total cost
```

If a task fails, MorningStar retries once using Claude Code's session resumption to preserve context from the first attempt.

---

## 24/7 Operation

MorningStar ships with a built-in queue processor (`morningstar process-queue`) and two GitHub Actions workflows that poll a Notion database and Jira project every 15 minutes, process any pending PRDs end-to-end, and open PRs automatically.

**Quick setup:**

1. Add a `Status` select column to your Notion DB with values `Pending | Running | Done | Failed`.
2. In Jira, label tickets you want picked up with `morningstar`.
3. Set repo-level GitHub **variables**: `MORNINGSTAR_ENV`, `MORNINGSTAR_NOTION_DB_ID`, `MORNINGSTAR_JIRA_URL`, `MORNINGSTAR_JIRA_PROJECT_KEY`, `MORNINGSTAR_WEEKLY_BUDGET`, `MORNINGSTAR_TARGET_REPO`.
4. Set repo-level GitHub **secrets**: `ANTHROPIC_API_KEY`, `MORNINGSTAR_NOTION_TOKEN`, `MORNINGSTAR_JIRA_EMAIL`, `MORNINGSTAR_JIRA_TOKEN`, `MORNINGSTAR_SLACK_WEBHOOK`, `MORNINGSTAR_TARGET_REPO_TOKEN`.
5. First scheduled run fires within 15 min. Watch the Actions tab.

See [HANDOVER.md](HANDOVER.md) for the complete runbook and [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for the 24/7 setup walkthrough.

---

## Security

MorningStar executes code in your repository with full shell access. Before running:

- **Review the PRD** -- PRD content influences agent behavior
- **Use `--dry-run`** to preview tasks before execution
- **Set budget limits** to cap spending
- **Run in isolation** (VM/container) for untrusted PRDs

See [SECURITY.md](SECURITY.md) for the full security model and vulnerability reporting.

---

## Slack Updates

MorningStar posts to your Slack channel at every step:

```
MorningStar started. Reading PRD from Notion...
Found 7 tasks to implement. Starting work...
[1/7] Starting: Implement attendance analytics service
[1/7] Completed: Implement attendance analytics service ($1.80)
[2/7] Starting: Add homework analytics endpoints
[2/7] Completed: Add homework analytics endpoints ($1.50)
...
MorningStar complete: 7 done, 0 failed. Cost: $12.50/$50.00
```

---

## Logs

All agent output is saved to `<repo>/.agent-logs/`:

| File | Content |
|------|---------|
| `prd.md` | Full PRD text fetched from Notion |
| `tasks.json` | Generated task list |
| `task-<id>.json` | Claude's full output per task |
| `task-<id>-retry.json` | Retry output (if task failed first attempt) |
| `task-<id>-answer.json` | Follow-up output after Slack Q&A |

---

## Development

```bash
pip install -e ".[dev]"
ruff check src/
mypy src/
pytest
```

---

## Environment

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key |
| `MORNINGSTAR_SLACK_WEBHOOK` | No | Slack webhook (alternative to CLI flag) |
| `MORNINGSTAR_SLACK_BOT_TOKEN` | No | Bot token for two-way Q&A (`xoxb-...`) |
| `MORNINGSTAR_SLACK_CHANNEL` | No | Channel ID for posting questions |

The Claude Code CLI must be authenticated (`claude auth login`).

---

## License

MIT
