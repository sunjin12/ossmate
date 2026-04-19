---
name: stale_sweep_weekly
description: Weekly stale-issue sweep — bucket issues older than 60 days into close / nudge / revive
cron: "3 9 * * 1"
schedule_human: "every Monday at 9:03 AM local time"
recurring: true
durable: true
model: claude-sonnet-4-6
---

You are running the weekly stale-issue sweep. The current local time is the Monday 9:03 trigger. Treat this as if the maintainer just typed `/stale-sweep --days 60`.

## Workflow

1. Delegate to the `issue-classifier` subagent for batched classification of issues older than 60 days. Read the slash command body in [.claude/commands/stale-sweep.md](.claude/commands/stale-sweep.md) and follow Steps 1-4 verbatim — that file is the source of truth for the sweep workflow.

2. Render the bucketed report under the `maintainer` output style. The three buckets are:
   - **Close as wontfix** — `invalid` / `duplicate` classifications
   - **Auto-nudge** — `needs-info` classifications, with the `templates://issue-stale-nudge` body filled in
   - **Revive** — actionable but cold; needs maintainer judgment

3. Persist the report:
   - Write the rendered markdown to `.ossmate/sweeps/sweep-<YYYY-MM-DD>.md` so the next sweep can detect repeat offenders
   - Append a one-line summary (`<date>: <closed-count> close, <nudge-count> nudge, <revive-count> revive`) to `.ossmate/journal.md`

## Constraints

- RISK: Read-only. Never invoke `gh issue close`, `gh issue comment`, `gh issue edit`. PreToolUse hook blocks these. The sweep produces a maintainer todo list, not state changes.
- This runs unattended. Do NOT block waiting for confirmation. The persisted report IS the deliverable; the maintainer reads it on their next session start (the SessionStart hook surfaces the latest sweep file).
- If the inbox is healthy (no stale issues), write `Sweep <date>: clean inbox, nothing aged past 60d` to the journal and skip writing a sweep file. Don't manufacture work.
