---
description: Deep security review of a single PR — secrets, injection, auth, supply chain, CI workflows
argument-hint: <pr-number> [--focus auth,ci,...]
allowed-tools: Bash(gh pr view:*) Bash(gh pr diff:*) Bash(gh api:*) Bash(git log:*) Bash(git diff:*) Read Grep Glob Task
model: claude-opus-4-7
---

# /security-review-pr

You are running a security review on PR **$1**. This is the heaviest skill in the toolkit; only invoke when the PR genuinely warrants it.

> If `$1` is empty, stop and ask.

## Workflow

### Step 1 — Justification check

Run `!gh pr view $1 --json files,labels`. Confirm at least one of:
- The PR touches `.github/workflows/`, `.claude/hooks/`, `.claude/settings.json`
- The PR modifies `package.json` / `pyproject.toml` / `Cargo.toml` (dependency changes)
- The PR touches paths matching `**/auth*`, `**/secret*`, `**/crypto*`, `**/login*`, `**/permission*`
- The PR has a `RISK:` or `security` label
- The user explicitly invoked this skill (i.e., took the action knowingly)

If none of those hold AND the user did not pass an explicit `--force` flag, suggest `/triage-pr $1` instead and stop. Save tokens.

### Step 2 — Delegate to `security-reviewer`

Parse `$ARGUMENTS` for `--focus <areas>` (comma-separated).

Invoke the `security-reviewer` subagent via the Task tool, passing:
- `pr_number`: $1
- `repo`: result of `gh repo view --json nameWithOwner`
- `focus_areas`: parsed list, or `null`

This subagent runs on `opus` and is slow (~minutes). Tell the user up-front: `security review delegated to opus — this takes a minute or two`.

### Step 3 — If supply-chain changes detected, also call `dep-auditor`

If `gh pr view --json files` includes any lockfile (`package-lock.json`, `poetry.lock`, `uv.lock`, `Cargo.lock`), invoke `dep-auditor` IN PARALLEL with `security-reviewer`. Add its output as an `## Advisory cross-check` section so the maintainer can see whether the new deps are clean.

### Step 4 — Synthesize

Present `security-reviewer`'s output verbatim (it's already `maintainer`-style). If `dep-auditor` ran, append its table. Lead with the highest severity finding.

If verdict is `block`, lead with:

```
RISK: blocking security findings on PR #$1. Do NOT merge until resolved.
```

### Step 5 — Wait

Do NOT post the review, comment, or merge. Even when findings are clean, the maintainer reviews and acts.

## Constraints

- RISK: Never invoke `gh pr review --approve|--request-changes`, `gh pr comment`, `gh pr merge`. PreToolUse hook blocks these.
- Never silently approve unknown third-party deps. If the subagent flagged a dep as unverifiable, surface it as a `Decisions needed` checkbox.
- Do NOT skip the `security-reviewer`'s checklist sections. If it says "No findings in: <X>", show that — the maintainer needs to know what was checked AND what was not.
