# ossmate (CLI)

Standalone CLI version of [Ossmate](https://github.com/sunjin12/ossmate), built on the [Claude Agent SDK](https://docs.anthropic.com/en/api/agent-sdk). Use it from your terminal, CI, or anywhere outside Claude Code.

## Install

```bash
pipx install ossmate
```

## Commands (planned — Phase 7)

```bash
ossmate triage [--since 24h] [--repo owner/name]
ossmate release-notes --tag vX.Y.Z
ossmate stale-sweep [--days 60] [--dry-run]
ossmate audit-deps
ossmate onboard <github-username>
```

## Configuration

`~/.config/ossmate/config.toml`:

```toml
default_repo = "owner/name"

[anthropic]
# Falls back to ANTHROPIC_API_KEY env var
api_key = "sk-..."

[github]
# Falls back to GITHUB_TOKEN env var
token = "ghp_..."
```
