---
description: Audit lockfiles for known vulnerabilities (OSV.dev) and surface stale direct deps
argument-hint: [--ecosystem npm|pypi|crates.io]
allowed-tools: Bash(git ls-files:*) Bash(git status:*) Read Grep Glob Task
model: claude-sonnet-4-6
---

# /audit-deps

You are auditing this project's dependencies.

## Workflow

### Step 1 — Confirm scope

Parse `$ARGUMENTS` for `--ecosystem <name>`. Defaults to all detected ecosystems.

Run `!git ls-files | grep -E "(package-lock\.json|poetry\.lock|uv\.lock|Cargo\.lock|yarn\.lock|pnpm-lock\.yaml)$"` to confirm which lockfiles exist. If none, report `No lockfile found — nothing to audit.` and stop.

### Step 2 — Delegate to `dep-auditor`

Invoke the `dep-auditor` subagent via the Task tool, passing:
- `path`: `${CLAUDE_PROJECT_DIR}` (project root)
- `ecosystem_filter`: from `--ecosystem` flag, or `null`

The subagent uses the Ossmate MCP server (`mcp__ossmate__read_lockfile` + `mcp__ossmate__check_advisories`) to do the OSV.dev batched query.

### Step 3 — Present unchanged

The `dep-auditor` already produces `maintainer`-style output. Pass it through without re-summarizing.

### Step 4 — Decisions

If any advisory is `HIGH` or `CRITICAL`, lead the response with:

```
RISK: <K> high/critical advisories found. Cutting a release before resolving these is not safe.
```

Then the subagent's report. Then:

```
**Decisions needed**
- [ ] For each `RISK:` row in the table — bump the dependency? File a tracking issue? Vendor-pin a workaround?

**Mechanical (after approval)**
- [ ] Open issues for any advisory the maintainer wants to track separately
```

## Constraints

- RISK: Never run `npm install`, `npm audit fix`, `poetry update`, `cargo update`, or any command that mutates lockfiles. Read-only.
- If MCP is unavailable, the subagent will report `{"error": "no_advisory_source"}` — surface that to the user verbatim. Don't pretend the audit succeeded.
- If a lockfile is committed but its manifest is not (or vice versa), call that out as `RISK:` — it indicates a misconfigured project.
