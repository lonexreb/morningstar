---
description: Previews the MorningStar task plan for a PRD without writing any code or making commits. Fetches the Notion PRD, analyzes the current codebase, and prints the proposed task list with files, acceptance criteria, and an estimated cost. Use when the user says any of "preview", "dry run", "what would this build", "show me the plan", "estimate cost", "morningstar dry-run", or wants to validate a PRD before triggering a real run. Read-only and free to invoke.
argument-hint: <notion-url>
---

# MorningStar Dry Run

Fetch a Notion PRD and generate a task plan without executing anything. Use this to preview what the agent would do before committing to a full run.

## Arguments

User provided: $ARGUMENTS

Parse the **notion-url** (required): Notion page URL or ID containing the PRD.

## Instructions

1. **Fetch the PRD** from the provided Notion URL
2. **Analyze the codebase** in the current working directory
3. **Generate a task list** of what needs to be built
4. **Display the plan** as a numbered list with:
   - Task ID
   - Title
   - Files to modify
   - Acceptance criteria
5. **Do NOT execute** any tasks, write any code, or make any commits
6. Report the estimated number of tasks and approximate cost

## Example

```
/morningstar:dry-run https://notion.so/My-PRD-abc123
```
