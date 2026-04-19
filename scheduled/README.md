# Scheduled triggers

Three Claude-managed cron jobs that automate the recurring parts of OSS maintenance.

| File | Cadence | What it does |
|---|---|---|
| [daily_digest.md](daily_digest.md) | daily 8:57 AM | Digest of open PRs needing review, new issues, fresh advisories |
| [stale_sweep_weekly.md](stale_sweep_weekly.md) | Mondays 9:03 AM | Bucket issues older than 60d into close / nudge / revive |
| [release_radar.md](release_radar.md) | Fridays 8:47 AM | Propose next semver bump and flag release blockers |

## Why these times?

All three pick **off-minute** marks (`:57`, `:03`, `:47`) instead of `:00` / `:30`. Every Claude user who asks for "9 AM" gets `0 9 * * *`, so the API sees a thundering herd at the top of the hour — picking minute 47 / 57 / 03 spreads the load and avoids rate-limit windows. The maintainer cannot tell the difference; the fleet can.

## Schema

Each `*.md` file has YAML frontmatter and a markdown body:

```yaml
---
name: <kebab_or_snake_name>           # required, matches filename stem
description: <one line>               # required
cron: "M H DoM Mon DoW"               # required, standard 5-field cron in local time
schedule_human: "every Monday at..."  # required, human-readable mirror of `cron`
recurring: true | false               # required
durable: true | false                 # true = persists across Claude restarts
model: claude-<model-id>              # optional, override default model
---

<markdown body — sent verbatim as the prompt to Claude when the cron fires>
```

The body must be self-contained: scheduled jobs run unattended, so it cannot ask follow-up questions or wait for confirmation. Treat it as the user's only message.

## Activating the schedules

The definitions in this directory are inert files on disk. To register them with Claude's scheduler, ask Claude:

```
Read each scheduled/*.md file and call CronCreate for each, using the `cron` and the body as the prompt. Set durable: true so they survive across sessions.
```

Claude will:
1. Walk `scheduled/*.md`
2. Parse each frontmatter
3. Call `CronCreate(cron=<expr>, prompt=<body>, recurring=true, durable=true)` for each

After registration, `CronList` shows them. To remove one, pass its job ID to `CronDelete`.

> Recurring jobs auto-expire after 7 days per Claude's scheduler policy. Re-run the activation prompt weekly, or use `RemoteTrigger` for production-grade scheduling backed by claude.ai.

## Why three jobs and not more?

Same reason a maintainer doesn't want eight calendar invites per week:
- **Daily digest** = morning context (1 minute to read)
- **Weekly stale sweep** = inbox hygiene (10 minutes to act on)
- **Weekly release radar** = ship-readiness check (5 minutes to decide)

Anything more frequent crosses the threshold from "useful nudge" to "noise the maintainer mutes."
