---
description: Find issues older than N days with no recent activity, classify each, propose nudge / close / wontfix
argument-hint: [--days N] [--label <label>]
allowed-tools: Bash(gh issue list:*) Bash(gh issue view:*) Bash(gh repo view:*) Read Grep Glob Task
model: claude-sonnet-4-6
---

# /stale-sweep

You are sweeping stale issues for this repository.

## Workflow

### Step 1 — Parse arguments

Defaults: `days=60`, `label=""`. Parse `$ARGUMENTS` for `--days <N>` and `--label <name>`.

### Step 2 — Find stale issues

Compute the cutoff date: today - `days`. Run:

```
!gh issue list --state open --search "updated:<<CUTOFF>>" --json number,title,author,labels,createdAt,updatedAt --limit 50
```

(Use `--label` filter if provided.)

If no issues match, report `No stale issues older than <days>d. Inbox is healthy.` and stop. Don't manufacture work.

### Step 3 — Classify in bulk via `issue-classifier`

For each stale issue, gather minimal context (`gh issue view <n> --json number,title,body,author,labels,createdAt,updatedAt`) and invoke the `issue-classifier` subagent. Fan out in parallel — `issue-classifier` runs on `haiku` and is cheap. Cap concurrency at 5.

### Step 4 — Bucket and present

Group results into three buckets:

```
Found <N> stale issues older than <days>d.

**Decisions needed (close as wontfix?)**
- [ ] [#142](#) "..." — classification: <X>, last activity <Y>d ago, author inactive
- [ ] ...

**Decisions needed (revive — author active, still relevant)**
- [ ] [#198](#) "..." — propose nudge with the `templates://issue-stale-nudge` template
- [ ] ...

**Auto-nudge candidates (mechanical, after approval)**
- [ ] [#234](#) "..." — needs-info, send templated nudge
- [ ] ...
```

Bucketing rules:
- `invalid`, `duplicate` → close-as-wontfix bucket.
- `needs-info` → auto-nudge bucket.
- everything else (`bug`, `feature`, `enhancement`, `question`, `docs`) → revive bucket. The maintainer must judge whether to close or push to next milestone.

### Step 5 — Wait

Do NOT close, comment, or label. The user picks which actions to apply.

## Constraints

- RISK: Never invoke `gh issue close`, `gh issue comment`, `gh issue edit`. PreToolUse hook blocks these.
- If you find more than 30 stale issues, present the top 10 of each bucket and tell the user how many were truncated. Don't overwhelm.
- If `gh issue list` fails, report the error and stop. Don't assume an empty inbox.
