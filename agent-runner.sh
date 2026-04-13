#!/bin/bash
set -euo pipefail

# ============================================================
# Autonomous Coding Agent Runner
#
# Takes a Notion PRD, a Slack webhook, and a repo path.
# Reads the PRD, diffs against codebase, generates tasks,
# then implements each task autonomously using Claude Code CLI.
#
# Usage:
#   ./agent-runner.sh \
#     --notion-url "https://notion.so/PRD-abc123" \
#     --slack-webhook "https://hooks.slack.com/services/..." \
#     --repo "/path/to/repo"
#
# Environment variables (optional):
#   AGENT_MODEL              - Claude model (default: sonnet)
#   AGENT_MAX_BUDGET_PER_TASK - Max USD per task (default: 5.00)
#   AGENT_TOTAL_BUDGET       - Total USD budget (default: 50.00)
#   ANTHROPIC_API_KEY        - Required by Claude CLI
# ============================================================

# --- Parse arguments ---
NOTION_URL=""
SLACK_WEBHOOK=""
REPO_PATH=""
MODEL="${AGENT_MODEL:-sonnet}"
BUDGET_PER_TASK="${AGENT_MAX_BUDGET_PER_TASK:-5.00}"
TOTAL_BUDGET="${AGENT_TOTAL_BUDGET:-50.00}"

while [[ $# -gt 0 ]]; do
  case $1 in
    --notion-url)    NOTION_URL="$2"; shift 2 ;;
    --slack-webhook) SLACK_WEBHOOK="$2"; shift 2 ;;
    --repo)          REPO_PATH="$2"; shift 2 ;;
    --model)         MODEL="$2"; shift 2 ;;
    --budget)        TOTAL_BUDGET="$2"; shift 2 ;;
    --help|-h)
      echo "Usage: ./agent-runner.sh --notion-url URL --slack-webhook URL --repo PATH"
      echo ""
      echo "Options:"
      echo "  --notion-url    Notion page URL or ID containing the PRD"
      echo "  --slack-webhook Slack incoming webhook URL for status updates"
      echo "  --repo          Path to the target repository"
      echo "  --model         Claude model to use (default: sonnet)"
      echo "  --budget        Total USD budget for the run (default: 50.00)"
      exit 0 ;;
    *) echo "Unknown arg: $1. Use --help for usage."; exit 1 ;;
  esac
done

if [[ -z "$NOTION_URL" || -z "$SLACK_WEBHOOK" || -z "$REPO_PATH" ]]; then
  echo "Error: --notion-url, --slack-webhook, and --repo are all required."
  echo "Run ./agent-runner.sh --help for usage."
  exit 1
fi

# Resolve to absolute path
REPO_PATH=$(cd "$REPO_PATH" && pwd)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROMPT_FILE="$SCRIPT_DIR/agent-prompt.md"
LOG_DIR="$REPO_PATH/.agent-logs"
STATE_FILE="$LOG_DIR/state.json"
mkdir -p "$LOG_DIR"

# Counters (use a state file to survive subshell issues)
echo '{"completed":0,"failed":0,"cost":0}' > "$STATE_FILE"

# --- Helpers ---
slack_post() {
  curl -s -X POST "$SLACK_WEBHOOK" \
    -H 'Content-type: application/json' \
    -d "$(jq -n --arg text "$1" '{text: $text}')" > /dev/null 2>&1 || true
}

add_cost() {
  local new_cost
  new_cost=$(jq -r ".cost + $1" "$STATE_FILE" 2>/dev/null || echo "0")
  jq ".cost = $new_cost" "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
}

get_cost() {
  jq -r '.cost' "$STATE_FILE" 2>/dev/null || echo "0"
}

inc_completed() {
  jq '.completed += 1' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
}

inc_failed() {
  jq '.failed += 1' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
}

check_budget() {
  local current total over
  current=$(get_cost)
  total="$TOTAL_BUDGET"
  over=$(echo "$current >= $total" | bc 2>/dev/null || echo "0")
  if [[ "$over" == "1" ]]; then
    slack_post "Budget limit reached (\$${current}/\$${total}). Stopping."
    echo "BUDGET EXCEEDED: \$${current} >= \$${total}"
    exit 0
  fi
}

ts() {
  date '+%Y-%m-%d %H:%M:%S'
}

log() {
  echo "[$(ts)] $1"
}

# Build system prompt args
SYSTEM_PROMPT_ARGS=()
if [[ -f "$PROMPT_FILE" ]]; then
  SYSTEM_PROMPT_ARGS=(--append-system-prompt "$(cat "$PROMPT_FILE")")
fi

# ============================================================
# Step 1: Read PRD from Notion
# ============================================================
log "Step 1: Fetching PRD from Notion..."
slack_post "Agent started. Reading PRD from Notion..."

PRD_RESULT=$(claude -p "Fetch the content of this Notion page and return the FULL text, preserving all sections, headings, tables, and details. Do not summarize -- return everything. Page URL or ID: $NOTION_URL" \
  --output-format json \
  --max-budget-usd 1.00 \
  --permission-mode dontAsk \
  --model "$MODEL" \
  "${SYSTEM_PROMPT_ARGS[@]}" 2>/dev/null) || PRD_RESULT='{"result":"ERROR: Could not fetch PRD","is_error":true,"total_cost_usd":0}'

PRD_TEXT=$(echo "$PRD_RESULT" | jq -r '.result // "ERROR"')
PRD_COST=$(echo "$PRD_RESULT" | jq -r '.total_cost_usd // 0')
add_cost "$PRD_COST"

if [[ "$PRD_TEXT" == "ERROR" ]] || echo "$PRD_RESULT" | jq -e '.is_error == true' > /dev/null 2>&1; then
  slack_post "Failed to fetch PRD from Notion. Check the URL and MCP configuration."
  log "ERROR: Could not fetch PRD. Raw output saved to $LOG_DIR/prd-error.json"
  echo "$PRD_RESULT" > "$LOG_DIR/prd-error.json"
  exit 1
fi

echo "$PRD_TEXT" > "$LOG_DIR/prd.md"
log "PRD fetched ($(echo "$PRD_TEXT" | wc -l | tr -d ' ') lines, \$$PRD_COST)"

# ============================================================
# Step 2: Analyze codebase and generate task list
# ============================================================
log "Step 2: Analyzing codebase and generating tasks..."
slack_post "PRD loaded. Analyzing codebase to identify gaps..."

TASK_SCHEMA='{"type":"object","properties":{"tasks":{"type":"array","items":{"type":"object","properties":{"id":{"type":"string"},"title":{"type":"string"},"description":{"type":"string"},"acceptance_criteria":{"type":"string"},"test_command":{"type":"string"}},"required":["id","title","description"]}}},"required":["tasks"]}'

TASKS_RESULT=$(cd "$REPO_PATH" && claude -p "You have access to this codebase at $REPO_PATH. Here is the PRD:

--- PRD START ---
$PRD_TEXT
--- PRD END ---

Analyze the codebase thoroughly. Read CLAUDE.md, README.md, and key source files. Identify what features from the PRD are NOT yet implemented or are incomplete.

Create a task list of concrete, implementable work items. Each task should be small enough to complete in one session (1-3 files changed). Order tasks by dependency (prerequisite tasks first).

For each task:
- id: short kebab-case identifier (e.g. 'analytics-service', 'attendance-chart')
- title: one-line human-readable description
- description: what exactly to implement, which files to create/modify, what existing patterns to follow
- acceptance_criteria: how to verify the task is done
- test_command: shell command to run tests (e.g. 'pnpm --filter api test' or 'pnpm build')" \
  --output-format json \
  --json-schema "$TASK_SCHEMA" \
  --max-budget-usd 3.00 \
  --allowedTools "Read,Glob,Grep,Bash" \
  --permission-mode dontAsk \
  --model "$MODEL" \
  "${SYSTEM_PROMPT_ARGS[@]}" 2>/dev/null) || TASKS_RESULT='{"structured_output":{"tasks":[]},"is_error":true,"total_cost_usd":0}'

TASKS_COST=$(echo "$TASKS_RESULT" | jq -r '.total_cost_usd // 0')
add_cost "$TASKS_COST"

# Extract structured task list (try structured_output first, then parse result)
TASKS=$(echo "$TASKS_RESULT" | jq '.structured_output.tasks // empty' 2>/dev/null)
if [[ -z "$TASKS" || "$TASKS" == "null" ]]; then
  TASKS=$(echo "$TASKS_RESULT" | jq -r '.result' 2>/dev/null | jq '.tasks // empty' 2>/dev/null || true)
fi
if [[ -z "$TASKS" || "$TASKS" == "null" ]]; then
  slack_post "Failed to generate task list from codebase analysis."
  log "ERROR: Could not parse tasks. Raw output saved to $LOG_DIR/tasks-error.json"
  echo "$TASKS_RESULT" > "$LOG_DIR/tasks-error.json"
  exit 1
fi

TASK_COUNT=$(echo "$TASKS" | jq 'length')
echo "$TASKS" | jq '.' > "$LOG_DIR/tasks.json"

log "Generated $TASK_COUNT tasks (\$$TASKS_COST)"
slack_post "Found $TASK_COUNT tasks to implement. Starting work..."

# ============================================================
# Step 3: Execute each task
# ============================================================
TASK_INDEX=0
echo "$TASKS" | jq -c '.[]' | while IFS= read -r task; do
  TASK_INDEX=$((TASK_INDEX + 1))
  TASK_ID=$(echo "$task" | jq -r '.id')
  TASK_TITLE=$(echo "$task" | jq -r '.title')
  TASK_DESC=$(echo "$task" | jq -r '.description')
  TASK_AC=$(echo "$task" | jq -r '.acceptance_criteria // "Tests pass"')
  TASK_TEST=$(echo "$task" | jq -r '.test_command // ""')

  echo ""
  echo "============================================================"
  log "[$TASK_INDEX/$TASK_COUNT] $TASK_ID: $TASK_TITLE"
  echo "============================================================"

  check_budget
  slack_post "[$TASK_INDEX/$TASK_COUNT] Starting: *$TASK_TITLE*"

  # Build prompt
  IMPL_PROMPT="Implement this task in the codebase:

Task: $TASK_TITLE
Description: $TASK_DESC
Acceptance Criteria: $TASK_AC

Rules:
- Read CLAUDE.md first for project conventions
- Follow existing codebase patterns exactly
- Write or update tests for your changes
- Run tests after making changes and fix any failures
- Do not modify unrelated code
- Do not add unnecessary dependencies"

  if [[ -n "$TASK_TEST" && "$TASK_TEST" != "null" ]]; then
    IMPL_PROMPT="$IMPL_PROMPT
- Run this test command to verify: $TASK_TEST"
  fi

  # Execute
  RESULT=$(cd "$REPO_PATH" && claude -p "$IMPL_PROMPT" \
    --output-format json \
    --max-budget-usd "$BUDGET_PER_TASK" \
    --allowedTools "Read,Write,Edit,Bash,Glob,Grep" \
    --permission-mode dontAsk \
    --model "$MODEL" \
    "${SYSTEM_PROMPT_ARGS[@]}" 2>/dev/null) || RESULT='{"is_error":true,"total_cost_usd":0,"result":"Agent process failed","session_id":""}'

  TASK_COST=$(echo "$RESULT" | jq -r '.total_cost_usd // 0')
  IS_ERROR=$(echo "$RESULT" | jq -r '.is_error // false')
  SESSION_ID=$(echo "$RESULT" | jq -r '.session_id // ""')
  add_cost "$TASK_COST"

  echo "$RESULT" > "$LOG_DIR/task-${TASK_ID}.json"

  # Retry once on error
  if [[ "$IS_ERROR" == "true" && -n "$SESSION_ID" && "$SESSION_ID" != "null" ]]; then
    log "Task $TASK_ID failed. Retrying with session context..."
    slack_post "Task *$TASK_TITLE* hit an error. Retrying..."

    RETRY_RESULT=$(cd "$REPO_PATH" && claude -p "The previous attempt had an error. Review what went wrong, fix it, and complete the task. Run tests to verify." \
      --output-format json \
      --resume "$SESSION_ID" \
      --max-budget-usd 3.00 \
      --allowedTools "Read,Write,Edit,Bash,Glob,Grep" \
      --permission-mode dontAsk 2>/dev/null) || RETRY_RESULT='{"is_error":true,"total_cost_usd":0}'

    RETRY_COST=$(echo "$RETRY_RESULT" | jq -r '.total_cost_usd // 0')
    IS_ERROR=$(echo "$RETRY_RESULT" | jq -r '.is_error // false')
    add_cost "$RETRY_COST"
    TASK_COST=$(echo "$TASK_COST + $RETRY_COST" | bc 2>/dev/null || echo "$TASK_COST")

    echo "$RETRY_RESULT" > "$LOG_DIR/task-${TASK_ID}-retry.json"
  fi

  # Commit changes if any exist
  cd "$REPO_PATH"
  if ! git diff --quiet HEAD 2>/dev/null || [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
    git add -A -- ':!.agent-logs'
    git commit -m "feat: $TASK_TITLE

Implemented by autonomous agent (task: $TASK_ID)
Cost: \$${TASK_COST}" 2>/dev/null || true
  fi

  if [[ "$IS_ERROR" == "true" ]]; then
    inc_failed
    slack_post "[$TASK_INDEX/$TASK_COUNT] Failed: *$TASK_TITLE* (\$$TASK_COST)"
    log "FAILED: $TASK_ID (\$$TASK_COST)"
  else
    inc_completed
    slack_post "[$TASK_INDEX/$TASK_COUNT] Completed: *$TASK_TITLE* (\$$TASK_COST)"
    log "DONE: $TASK_ID (\$$TASK_COST)"
  fi
done

# ============================================================
# Step 4: Final summary
# ============================================================
FINAL_COMPLETED=$(jq -r '.completed' "$STATE_FILE")
FINAL_FAILED=$(jq -r '.failed' "$STATE_FILE")
FINAL_COST=$(jq -r '.cost' "$STATE_FILE")

echo ""
echo "============================================================"
log "Agent run complete"
echo "  Tasks completed: $FINAL_COMPLETED"
echo "  Tasks failed:    $FINAL_FAILED"
echo "  Total cost:      \$$FINAL_COST"
echo "  Logs:            $LOG_DIR"
echo "============================================================"

slack_post "Agent run complete: *$FINAL_COMPLETED* completed, *$FINAL_FAILED* failed. Total cost: \$$FINAL_COST / \$$TOTAL_BUDGET budget."
