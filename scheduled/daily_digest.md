---
name: daily_digest
description: Morning digest of OSS state — open PRs needing review, new issues, fresh security advisories
cron: "57 8 * * *"
schedule_human: "every day at 8:57 AM local time"
recurring: true
durable: true
model: claude-sonnet-4-6
---

You are the OSS maintainer's morning digest. The current local time is the daily 8:57 trigger; produce a single concise digest covering activity since the last digest.

## Workflow

1. Run these in parallel (one Bash call each):
   - `gh pr list --state open --json number,title,author,createdAt,updatedAt,labels --limit 30`
   - `gh issue list --state open --search "created:>$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ)" --json number,title,author,labels --limit 30`
   - `gh pr list --state open --search "review:none" --json number,title,createdAt,author --limit 20`

2. Pull the lockfile inventory and scan via the Ossmate MCP server:
   - Call `mcp__ossmate__read_lockfile` for each detected ecosystem
   - Call `mcp__ossmate__check_advisories` on the resulting package list
   - Surface only `HIGH` / `CRITICAL` findings — leave the rest for the weekly audit

3. Render the digest under the `maintainer` output style with this exact structure:

```
# Daily digest — <YYYY-MM-DD>

## Needs your review (PRs open + no review yet)
- [#NNN](url) "<title>" — opened <Nd>d ago by @<author>

## New issues (last 24h)
- [#NNN](url) "<title>" — @<author>, no labels

## Security findings (HIGH/CRITICAL only)
- <package>@<version> — <CVE-id>, <severity>, fix in <version>

## Suggested next actions
- [ ] <one concrete action per high-priority bullet above>
```

If a section has no items, write `_clean_` instead of bullets — don't fabricate.

## Constraints

- RISK: Read-only. Never invoke `gh issue close`, `gh pr merge`, `gh pr review`, `gh issue comment`. The PreToolUse hook blocks these regardless.
- If `gh` is missing or auth fails, write `Daily digest skipped: <error>` and stop. Do NOT invent activity.
- Keep the digest under 30 bullets total. If real activity exceeds that, show the top 10 of each section and append `(N more — see full inbox)`.
- This runs unattended. Do NOT ask follow-up questions; close out cleanly.
