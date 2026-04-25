---
description: Implements a product requirements document (PRD) end-to-end. Reads the PRD from a Notion page, analyzes the current codebase, generates a task plan, and then implements each task with tests and git commits. Use when the user provides a Notion URL or says any of "implement this PRD", "build from requirements", "run morningstar", "ship this spec", "automate this feature", "turn this PRD into code", or "autonomous coding". Pushes progress to Slack at every task boundary when a webhook is provided.
argument-hint: <notion-url> [--model sonnet|opus|haiku] [--budget 50] [--slack-webhook https://hooks.slack.com/...]
---

# Run MorningStar

Execute the MorningStar autonomous coding agent. It reads a PRD from Notion, analyzes the current codebase, generates implementation tasks, and builds each one with tests and git commits.

## Arguments

User provided: $ARGUMENTS

Parse the following from arguments:
- **notion-url** (required): Notion page URL or ID containing the PRD
- **--model** (optional, default: sonnet): Claude model to use
- **--budget** (optional, default: 50): Total USD budget
- **--slack-webhook** (optional): Incoming webhook URL for progress updates. Falls back to `$MORNINGSTAR_SLACK_WEBHOOK`.

## Instructions

1. **Fetch the PRD** from the provided Notion URL using the Notion MCP tools.
2. **Analyze the codebase** in the current working directory:
   - Read CLAUDE.md and README.md for conventions
   - Explore project structure, key source files, and existing patterns
3. **Generate a task list** by diffing PRD requirements against what's already built
   - Each task: 1-3 files, concrete implementation, acceptance criteria
   - Order by dependency
4. **Show the task plan** and ask the user to confirm before executing.
5. **At task boundaries post to Slack** if a webhook is configured:
   - On start: `curl -X POST -H 'Content-type: application/json' --data '{"text":"[1/N] Starting: <title>"}' $WEBHOOK`
   - On completion: similar `Completed` or `Failed` message with cost.
6. **Execute each task**:
   - Implement code changes following existing patterns
   - Write/update tests
   - Run tests and fix failures
   - Git commit: `feat: <task title>`
   - Report progress
7. **Summarize**: tasks completed, tasks failed, any questions for the user. Post final summary to Slack.

## Example

```
/morningstar:run https://notion.so/My-PRD-abc123 --model opus --budget 100 --slack-webhook https://hooks.slack.com/services/T.../B.../xyz
```
