---
description: Triage a GitHub PR — read diff, classify scope/risk, propose labels, draft a review reply
argument-hint: <pr-number-or-url>
allowed-tools: Bash(gh pr view:*) Bash(gh pr diff:*) Bash(gh pr list:*) Bash(gh label list:*) Bash(gh repo view:*) Read Grep Glob Task
model: claude-sonnet-4-6
---

# /triage-pr

You are triaging PR **$1** as the OSS maintainer of this repository.

> If `$1` is empty, stop and ask the user for a PR number or URL. Do NOT guess.
> If `$1` looks like a URL (`https://github.com/owner/repo/pull/N`), extract `N`.

## Workflow

### Step 1 — Quick safety check (yourself, before delegation)

Run in parallel:
- `!gh pr view $1 --json number,title,additions,deletions,files,baseRefName,labels,mergeable,checks`
- `!gh repo view --json nameWithOwner`

Decide whether this PR warrants the cheap path or the expensive path:

- **Cheap path** (skip subagent): if additions + deletions < 50 AND files ≤ 3 AND mergeable AND CI green AND no `RISK:` label, just write a 3-line "approve-after-nits" verdict yourself and stop. Don't waste a subagent invocation.
- **Standard path** (delegate to `pr-triager`): everything else.
- **Security path** (escalate to `security-reviewer`): if PR touches `.github/workflows/`, `package.json`/`pyproject.toml`/`Cargo.toml`, `.claude/hooks/`, or any path matching `**/auth*`, `**/secret*`, `**/crypto*`. Also if `pr-triager` returns a `RISK:` finding.

### Step 2 — Delegate

Invoke the `pr-triager` subagent via the Task tool, passing:
- `pr_number`: $1
- `repo`: result of `gh repo view --json nameWithOwner`

If Step 1 flagged the security path, ALSO invoke `security-reviewer` in parallel with `focus_areas` derived from the changed paths.

### Step 3 — Synthesize

If you ran both subagents, present `pr-triager`'s verdict first, then `security-reviewer`'s findings as an attached `## Security review` section. If a security finding is `HIGH` or `CRITICAL`, override `pr-triager`'s verdict to `block` regardless of what it said.

If you only ran `pr-triager`, pass its output through unchanged. If you took the cheap path, just say so:

```
PR #$1 — trivial change, fast-tracking. Approve after these nits:
- [ ] <nit 1>
- [ ] <nit 2>
```

### Step 4 — Wait for user approval

Do NOT post the review, merge, or comment. The user reviews your output and runs the `gh` commands themselves.

## Constraints

- RISK: Never invoke `gh pr merge`, `gh pr review --approve|--request-changes`, `gh pr comment`, `gh pr edit`. The PreToolUse hook blocks these; do not even attempt.
- If `gh pr view` 404s or auth fails, report the exact error and stop. Do not invent diff contents.
- If the PR is in draft state, lead your reply with "draft — soft review only" so the contributor knows you didn't apply final-review rigor.
