# Autonomous Coding Agent

A single shell script that reads a PRD from Notion, analyzes a codebase, generates tasks, and implements them autonomously using Claude Code CLI. Posts progress and questions to Slack.

## Usage

```bash
./agent-runner.sh \
  --notion-url "https://notion.so/PRD-abc123" \
  --slack-webhook "https://hooks.slack.com/services/..." \
  --repo "/path/to/target/repo"
```

## How It Works

1. Fetches PRD from Notion via Claude Code + MCP
2. Analyzes the target codebase, diffs against PRD requirements
3. Generates a structured task list (JSON) of what's missing
4. For each task: implements code, writes tests, runs tests, commits
5. Posts progress to Slack after each task
6. Retries failed tasks once with session context
7. Tracks cost and respects budget limits

## Files

- `agent-runner.sh` -- the entire product (~200 lines)
- `agent-prompt.md` -- system prompt that shapes agent behavior
- `.env.example` -- required environment variables

## Configuration

Set via environment variables or CLI flags:

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_MODEL` | `sonnet` | Claude model to use |
| `AGENT_MAX_BUDGET_PER_TASK` | `5.00` | Max USD per task |
| `AGENT_TOTAL_BUDGET` | `50.00` | Total USD budget for full run |
| `ANTHROPIC_API_KEY` | (required) | Anthropic API key |

## Logs

Agent logs are written to `<repo>/.agent-logs/`:
- `prd.md` -- fetched PRD content
- `tasks.json` -- generated task list
- `task-<id>.json` -- full Claude output per task
