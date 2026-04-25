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

[![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-Plugin-orange?logo=anthropic)](https://github.com/lonexreb/morningstar)
[![PyPI](https://img.shields.io/pypi/v/morningstar-agent.svg?label=pypi)](https://pypi.org/project/morningstar-agent/)
[![Python](https://img.shields.io/pypi/pyversions/morningstar-agent.svg)](https://pypi.org/project/morningstar-agent/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-117%20passing-brightgreen)](tests/)

**MorningStar is an autonomous coding agent for [Claude Code](https://claude.ai/code) that turns Notion and Jira PRDs into shipped pull requests.**

Give it a Notion page (or a Jira ticket) and a target repo. It reads the requirements, analyzes your codebase, generates an ordered task plan, and implements each task with tests, git commits, and per-step Slack updates -- ending with a PR you can review. A built-in 24/7 queue processor runs the same loop on a 15-minute GitHub Actions cron, asking questions in Slack when it gets stuck.

> **Keywords:** Claude Code plugin, autonomous coding agent, PRD-to-code, Notion to GitHub, Jira to PR, background coding agent, AI software engineer, anthropic claude code agent, autonomous SWE, async coding agent.

---

## Install

### As a Claude Code Plugin (recommended)

Inside any Claude Code session:

```
/plugin marketplace add lonexreb/morningstar
/plugin install morningstar@morningstar
```

Or, install directly from GitHub without registering the marketplace:

```
/plugin install morningstar@https://github.com/lonexreb/morningstar
```

Then drive it from the prompt:

```
/morningstar:run https://notion.so/Your-PRD-abc123
/morningstar:dry-run https://notion.so/Your-PRD-abc123
/morningstar:watch          # poll the 24/7 queue on demand
/morningstar:version
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

## Demo (no credentials required)

Want to see the queue processor end-to-end without setting up Notion, Jira, or Slack? Run the standalone demo:

```bash
python morningstar_demo.py
```

The script spins up a temporary git repo, mocks every external integration (Notion, Jira, Claude API, GitHub), drives a fake "Add hello world endpoint" PRD through the full state machine, and prints a narrated summary including simulated cost, status transitions, and PR creation. Tear-down is automatic.

Use this to:

- Validate a fresh install before configuring credentials
- Walk a stakeholder through the pipeline live
- Sanity-check the engine after pulling new changes

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

## Use Cases

MorningStar is built for teams who already write specs in Notion or Jira and want to compress the time between "spec approved" and "PR opened" without giving up review.

- **Async PRD execution** — drop a Notion page link in Slack, walk away, come back to a PR.
- **Backlog drainer** — label sufficiently scoped Jira tickets with `morningstar`; the 24/7 cron picks them up and ships PRs while you sleep.
- **CEO / PM-driven prototyping** — non-engineers file PRDs in Notion; engineers review the resulting PR instead of building from scratch.
- **Internal tools and glue work** — small services, integrations, scripts, dashboards, migrations.
- **Bug-fix sprints** — file a one-paragraph repro PRD per bug; let the agent run them in batch overnight.
- **Documentation refreshes** — point it at a doc site and a "rewrite for X" PRD.
- **Refactor checkpoints** — small, self-contained refactors framed as a PRD with acceptance criteria.

Not a fit for: research-heavy spikes, cross-repo refactors, or PRDs that require human judgement on every change. MorningStar opens a PR -- it does not merge.

---

## FAQ

**Q: How is MorningStar different from a Claude Code skill or a one-shot agent?**
MorningStar is a *workflow*, not a single prompt. It owns the full loop: PRD ingestion → codebase analysis → task planning → per-task implementation with tests → git commit → Slack progress → PR. The 24/7 queue processor runs the same loop unattended on a cron.

**Q: Does it run on Claude Code, the API, or both?**
Both. The plugin form runs inside Claude Code (recommended for interactive use). The standalone CLI shells out to `claude -p` in headless mode and works in CI / GitHub Actions.

**Q: How does it avoid runaway spend?**
Three layers of budget: per-task budget, per-run budget, and a weekly ledger persisted to the repo (for the 24/7 mode). The agent stops as soon as any limit is hit and posts a Slack notice.

**Q: What about secrets in PRDs or generated code?**
`git add` is run with explicit excludes for `.env`, `*.pem`, `*.key`, `credentials.json`, and `*secret*` patterns. PRD fetch and task generation run in read-only tool modes (no Bash). Only execution gets write + Bash. See [SECURITY.md](SECURITY.md).

**Q: Can the agent ask me questions when it's stuck?**
Yes. Provide a Slack bot token and channel ID; the agent posts blocking questions there and waits up to `--question-timeout` seconds for a reply. If no reply, it proceeds with the documented default. See [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

**Q: Does it work with Jira, or only Notion?**
Both. The 24/7 queue scans a Notion database (`Status == Pending`) *and* a Jira project (`label == morningstar AND status == "To Do"`). PRs are opened against the configured target repo regardless of source.

**Q: What's the minimum repo I can point it at?**
Any git repo with a `CLAUDE.md` or `README.md` and tests it can run. Smaller, well-scoped codebases produce dramatically better task plans than monorepos.

**Q: How do I uninstall the plugin?**
Inside Claude Code: `/plugin uninstall morningstar` then optionally `/plugin marketplace remove morningstar`.

---

## Related

- [Claude Code documentation](https://code.claude.com/docs/) — Anthropic's official plugin / skills / agents reference.
- [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) — official plugin marketplace.
- [HANDOVER.md](HANDOVER.md) — operations runbook for the 24/7 system.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — engine internals.
- [docs/USER_GUIDE.md](docs/USER_GUIDE.md) — end-to-end setup walkthrough.

---

## License

MIT
