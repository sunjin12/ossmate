---
description: Draft Keep-a-Changelog release notes from merged PRs / commits since the last tag
argument-hint: <version> [--since <ref-or-date>]
allowed-tools: Bash(gh release list:*) Bash(gh pr list:*) Bash(git log:*) Bash(git tag:*) Bash(git describe:*) Read Grep Glob Edit Task
model: claude-sonnet-4-6
---

# /release-notes

You are drafting the release notes for version **$1**.

> If `$1` is empty, stop and ask the user for a version (e.g., `v1.4.0` or `1.4.0`).
> Strip a leading `v` for internal computation; preserve the user's spelling in the final output.

## Workflow

### Step 1 — Determine `since`

Parse `$ARGUMENTS` for `--since <value>`. If absent:

- Run `!gh release list --limit 1 --json tagName,publishedAt` and use the latest tag's `publishedAt` ISO date as `since`.
- If `gh release list` returns nothing, run `!git describe --tags --abbrev=0` and use that tag.
- If neither has output, this is the project's first release — use the date of the first commit (`!git log --reverse --pretty=format:"%aI" | head -1`).

State the chosen `since` in your final output so the maintainer can sanity-check.

### Step 2 — Delegate to `release-notes-writer`

Invoke the `release-notes-writer` subagent via the Task tool, passing:
- `version`: $1 (without leading `v`)
- `since`: the value from Step 1
- `repo`: result of `gh repo view --json nameWithOwner`

The subagent will return JSON with `bump_proposed`, `bump_evidence`, `section_markdown`, and `unmatched_commits`.

### Step 3 — Present + offer to apply

Present the subagent's `section_markdown` to the user under the `changelog` output style. Below it:

```
**Bump inference**: <bump_proposed> — <bump_evidence>

**Unmatched commits** (need manual decision):
- <subject 1>
- ...

**Decisions needed**
- [ ] Confirm version: $1
- [ ] Insert this block above `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md)?
- [ ] Move remaining items from `## [Unreleased]` into this section?
```

### Step 4 — Apply (only after confirmation)

If the user explicitly approves, use the Edit tool to:
1. Insert the new version section immediately above the existing `## [Unreleased]` line in [CHANGELOG.md](CHANGELOG.md).
2. Reset `## [Unreleased]` to an empty stub (heading only, no `### Added` etc.).

Do NOT commit. Do NOT tag. Do NOT run `gh release create`. Those are user actions.

## Constraints

- RISK: Never invoke `gh release create`, `git tag`, `git push --tags`. The PreToolUse hook blocks these.
- If `unmatched_commits` is non-empty, do NOT suppress them. The maintainer must see them and decide.
- If the proposed version would conflict with an existing tag (`!git tag -l "$1"` returns a match), warn loudly and do not edit the changelog.
