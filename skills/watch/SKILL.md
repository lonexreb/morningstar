---
description: Polls Notion and Jira for pending MorningStar PRDs and dispatches the GitHub Actions executor when work is found. Use when the user says any of "watch the queue", "poll for prds", "check queue", "trigger morningstar now", "is anything queued", "force a queue scan", or "morningstar 24/7 status". Safe to run on a schedule -- read-only against Notion/Jira, only writes a workflow_dispatch event and a Slack summary.
argument-hint: [--repo owner/name]
---

# Watch the MorningStar queue

Poll the Notion DB and Jira project for pending PRDs. If any are found, dispatch the `morningstar-scheduled.yml` GitHub Actions workflow and post a summary to Slack.

## Arguments

User provided: $ARGUMENTS

Optional:
- **--repo** (default: `lonexreb/morningstar`): GitHub `owner/name` for the executor workflow.

## Prerequisites the user has configured

- `MORNINGSTAR_NOTION_DB_ID`, `MORNINGSTAR_NOTION_TOKEN` (environment) -- for the Notion DB scan.
- `MORNINGSTAR_JIRA_URL`, `MORNINGSTAR_JIRA_EMAIL`, `MORNINGSTAR_JIRA_TOKEN`, `MORNINGSTAR_JIRA_PROJECT_KEY` -- for Jira.
- `gh` CLI authenticated (any of: `GH_TOKEN` env, `gh auth login`, or the Claude Code GitHub MCP).
- `MORNINGSTAR_SLACK_WEBHOOK` -- for the summary post.

## Instructions

1. **Scan Notion** using the Notion MCP tool:
   - Query database `$MORNINGSTAR_NOTION_DB_ID`
   - Filter: `Status == "Pending"`
   - Collect the row IDs and titles.

2. **Scan Jira** via WebFetch (or Jira MCP if installed):
   - `GET $MORNINGSTAR_JIRA_URL/rest/api/3/search?jql=project = $MORNINGSTAR_JIRA_PROJECT_KEY AND labels = "morningstar" AND status = "To Do"`
   - Basic auth with `$MORNINGSTAR_JIRA_EMAIL` / `$MORNINGSTAR_JIRA_TOKEN`.
   - Collect issue keys + summaries.

3. **Decide**:
   - If both lists are empty: post `MorningStar watcher: no pending items.` to Slack via webhook. Exit.
   - If non-empty: continue.

4. **Dispatch the executor**:
   ```
   gh workflow run morningstar-scheduled.yml --repo <target-repo> --field force_run=true
   ```
   Report the run URL if `gh` returns one.

5. **Post Slack summary**:
   ```
   MorningStar watcher: N pending items queued.
   - Notion: <count> (titles...)
   - Jira: <count> (issue keys...)
   Executor dispatched: <run URL>
   ```

6. **Exit quickly** -- this skill must stay under ~30 seconds so it's cheap to schedule.

## Recommended cadence

Register via the Claude Code `/schedule` tool as a recurring Cloud Task (hourly):

```
/schedule morningstar:watch --cron "0 * * * *"
```

The GitHub Actions executor (which is the actual runner) has its own 15-minute cron schedule, so this watcher is defense-in-depth -- it catches cases where the GH cron missed a fire or where we want a human-initiated poll.

## Example

```
/morningstar:watch --repo lonexreb/morningstar
```

Expected output:

```
Watcher scanned 2 pending items (1 Notion, 1 Jira).
Dispatched morningstar-scheduled.yml: https://github.com/.../actions/runs/123
Slack notified.
```
