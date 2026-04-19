# ossmate-mcp

MCP (Model Context Protocol) server that exposes OSS-maintainer tools to Claude Code and any other MCP-compatible client.

> Part of the [Ossmate](https://github.com/sunjin12/ossmate) project.

## Tools (planned — Phase 4)

- `github.list_open_prs(repo, limit)`
- `github.get_pr_diff(repo, number)`
- `github.list_merged_prs_since(repo, tag)`
- `github.list_stale_issues(repo, days)`
- `github.post_comment(repo, number, body)` — gated by Claude Code PreToolUse hook
- `changelog.parse(path)`
- `changelog.propose_bump(prs)` — Conventional Commits → semver
- `deps.read_lockfile(path)` — auto-detects npm / poetry / cargo
- `deps.check_advisories(deps)` — osv.dev cache
- `repo.detect_project_type(path)`
- `repo.list_recent_commits(since)`

## Resources (planned)

- `templates://release-notes`
- `templates://issue-stale-nudge`
- `templates://welcome`

## Install

```bash
pip install ossmate-mcp
```

## Use with Claude Code

The plugin install handles registration automatically. To register manually:

```bash
claude mcp add ossmate -- ossmate-mcp
```
