---
description: Inspect Conventional Commits since last tag and propose the next semver bump (no changelog edit)
argument-hint: [--since <ref-or-date>]
allowed-tools: Bash(git log:*) Bash(git describe:*) Bash(git tag:*) Bash(gh release list:*) Read Grep Glob
model: claude-sonnet-4-6
---

# /changelog-bump

You are computing the next semver bump for this project based on Conventional Commits since the last tag. **You do NOT edit any file.** This is a read-only inference.

For an actual changelog draft + edit, use `/release-notes <version>` instead.

## Workflow

### Step 1 — Determine `since`

Parse `$ARGUMENTS` for `--since <value>`. If absent:
- `!git describe --tags --abbrev=0` → use that tag.
- If no tags exist (`fatal: No names found`), use `--root` (since first commit).

### Step 2 — Determine current version

Read it from `pyproject.toml` (`[project] version = "..."`) or `package.json` (`"version": "..."`) or `Cargo.toml` (`[package] version = "..."`). If multiple manifests exist, prefer the project's primary language (use the Ossmate MCP `mcp__ossmate__detect_project_type` if available, else infer from the lockfile present). State which file you read from.

### Step 3 — Use the MCP tool

Call `mcp__ossmate__propose_bump` with:
- `current_version`: from Step 2
- `since`: from Step 1
- `repo_path`: `${CLAUDE_PROJECT_DIR}`

If MCP is unavailable, fall back to:
- `!git log <since>..HEAD --pretty=format:"%s" --no-merges` to get subjects.
- Apply the Conventional Commits rubric yourself (see below).

### Step 4 — Present

Use the `maintainer` output style:

```
Current version: <X.Y.Z> (from <manifest>)
Since: <ref-or-date> (<N> commits)
Proposed bump: <major|minor|patch|none> → <new version>
Evidence: <one sentence citing the commit>

**Commits classified**
- feat (minor): <count>
  - <subject>
- fix (patch): <count>
- breaking (major): <count>
  - <subject>
- chore/docs/test (no bump): <count>

**Unmatched** (do not follow Conventional Commits — manual review needed)
- <subject>
- ...

**Decisions needed**
- [ ] Accept proposed bump and run `/release-notes <new version>`?
- [ ] Or override (e.g., force minor for marketing reasons)?
```

## Conventional Commits rubric (fallback)

- `<type>!:` OR body contains `BREAKING CHANGE:` trailer → **major**
- `feat(...)` → **minor**
- `fix`, `perf`, `revert` → **patch**
- `docs`, `chore`, `test`, `refactor`, `style`, `ci`, `build` → **none**
- Anything not matching `^(<types>)(\([^)]+\))?!?: ` → unmatched, surface it

## Constraints

- This skill is strictly read-only. Do NOT edit `CHANGELOG.md`, `pyproject.toml`, `package.json`, `Cargo.toml`. That belongs to `/release-notes`.
- If the project has zero tags AND zero version field in any manifest, propose starting at `0.1.0` and say so explicitly.
- Never invent commit subjects. If `git log` is empty, report `No commits since <since> — no bump needed.` and stop.
