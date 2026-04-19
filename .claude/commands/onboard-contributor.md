---
description: Draft a warm welcome comment for a first-time contributor on their PR or issue
argument-hint: <pr-or-issue-number>
allowed-tools: Bash(gh pr view:*) Bash(gh issue view:*) Bash(gh pr list:*) Bash(gh issue list:*) Bash(gh repo view:*) Read Grep Glob Task
model: claude-haiku-4-5-20251001
---

# /onboard-contributor

You are drafting a welcome comment for the contributor who opened **#$1**.

> If `$1` is empty, stop and ask. Do NOT guess.

## Workflow

### Step 1 — Determine PR vs issue and find the author

Try `!gh pr view $1 --json number,title,author,createdAt` first. If it 404s, try `!gh issue view $1 --json number,title,author,createdAt`.

Capture the author's handle. If `gh pr view`/`gh issue view` both fail, report the error and stop.

### Step 2 — Verify "first-time" status

Run in parallel:
- `!gh pr list --author "<author>" --state all --json number --limit 5`
- `!gh issue list --author "<author>" --state all --json number --limit 5`

Count combined contributions. If the author has > 1 PR/issue, this is NOT a first-timer — tell the user, propose a normal triage instead, and stop.

### Step 3 — Gather project facts

Read [CONTRIBUTING.md](CONTRIBUTING.md) and [README.md](README.md) if they exist. Note:
- Response SLA (e.g., "we respond within 5 business days")
- CI link or workflow name
- Code of conduct reference

If `CONTRIBUTING.md` is missing, note that and tell the user the welcome will be more generic.

### Step 4 — Delegate to `community-greeter`

Invoke the `community-greeter` subagent via the Task tool, passing:
- `author`: the handle
- `repo`: `nameWithOwner`
- `number`: $1
- `summary`: PR/issue title
- `contributing_path`: path to CONTRIBUTING.md or `null`

### Step 5 — Present

Print the subagent's `comment_markdown` inside a fenced block labeled `<!-- proposed welcome comment -->`. Below it:

```
**Decisions needed**
- [ ] Apply label(s): `<labels_to_apply>` (only if they exist in the repo — verify with `gh label list`)
- [ ] Post the comment? (user runs `gh pr comment` or `gh issue comment` themselves)

**Follow-up actions**
- <follow_up_actions from subagent>
```

## Constraints

- RISK: Never invoke `gh pr comment`, `gh issue comment`, `gh issue edit`, `gh pr edit`. PreToolUse hook blocks these.
- Never invent project facts. If `CONTRIBUTING.md` doesn't exist, the welcome stays generic — that's fine.
- If the author is a bot (handle ends in `[bot]` or matches `dependabot|renovate|github-actions`), skip the welcome entirely and report `bot contributor — no greeting needed`.
