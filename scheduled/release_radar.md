---
name: release_radar
description: Friday release-readiness check — proposes the next semver bump and flags blockers
cron: "47 8 * * 5"
schedule_human: "every Friday at 8:47 AM local time"
recurring: true
durable: true
model: claude-sonnet-4-6
---

You are running the Friday release radar. The current local time is the Friday 8:47 trigger. Treat this as if the maintainer just typed `/changelog-bump`, then layered on a release-blocker check.

## Workflow

### Step 1 — Compute the proposed bump

Follow [.claude/commands/changelog-bump.md](.claude/commands/changelog-bump.md) Steps 1-3 verbatim. Capture:
- `current_version`
- `proposed_bump` (`major` / `minor` / `patch` / `none`)
- `proposed_version`
- `commit_count_since_last_tag`

### Step 2 — Gate on release blockers

Run in parallel:
- `gh pr list --state open --label "blocker,release-blocker" --json number,title --limit 20`
- `gh issue list --state open --label "blocker,release-blocker" --json number,title --limit 20`
- `mcp__ossmate__check_advisories` over the current lockfile (scope: HIGH/CRITICAL only)

### Step 3 — Verdict

If `proposed_bump == "none"` AND no blockers AND no critical advisories:
```
Release radar — <YYYY-MM-DD>: idle week. Current <current_version>, no notable commits, no blockers. Skip this Friday.
```

Otherwise render under the `maintainer` style:

```
# Release radar — <YYYY-MM-DD>

**Proposed bump**: <proposed_bump> → <proposed_version>
**Commits since <last_tag>**: <commit_count>
**Blockers**: <count>
**Critical advisories**: <count>

## Decisions needed
- [ ] Cut <proposed_version>? (If yes, run `/release-notes <proposed_version>`)
- [ ] Defer due to blockers: <list of blocker issue/PR numbers>
- [ ] Address advisories first: <list of CVE ids>

## Recent feat/fix commits (top 10)
- <subject>
```

### Step 4 — Persist

- Write the report to `.ossmate/release-radar/radar-<YYYY-MM-DD>.md`
- Append `<date>: bump=<proposed_bump>, blockers=<N>, advisories=<N>` to `.ossmate/journal.md`

## Constraints

- RISK: Strictly read-only. Never run `git tag`, `git push --tags`, `gh release create`, or edit `CHANGELOG.md` / version manifests. Those belong to `/release-notes` invoked by the maintainer.
- This runs unattended. Do NOT prompt for input. The maintainer reads the persisted radar file when convenient.
- If the project has zero tags, write `Release radar: pre-release project, manual versioning required.` and skip the bump computation. Don't propose `0.1.0` unprompted — that's a deliberate maintainer decision.
