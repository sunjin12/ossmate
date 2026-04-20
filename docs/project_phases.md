# Ossmate build phases

Ossmate was built incrementally in 10 phases (Phase 0 through Phase 9). Each phase produces an **independently demoable artifact** — development can stop at any phase boundary and still leave a shippable product. This gating rule kept scope from sprawling.

Every completed phase is tagged `phase-N` in git so you can `git checkout phase-5` to see the repo's state at that snapshot.

## Phase plan

| Phase | Deliverable |
|---|---|
| 0 | `git init`, two `pyproject.toml` (CLI + MCP), LICENSE, `.gitignore`, README skeleton, minimal `.claude/settings.json` + `CLAUDE.md` |
| 1 | Output style (`maintainer`, `changelog`) + `statusline.{sh,cmd}` + keybindings sample (immediate visual feedback) |
| 2 | First Skill `/triage-issue` — Bash-only, no MCP yet (learn frontmatter + `allowed-tools`) |
| 3 | Five hooks: PreToolUse guard, PostToolUse audit, UserPromptSubmit router, SessionStart brief, Stop summary |
| 4 | MCP server `ossmate_mcp` on FastMCP (started with `repo.detect_project_type`, grew to 11 tools + 3 resource templates) |
| 5 | Six subagents (Haiku / Sonnet / Opus tier) + remaining seven skills refactored to delegate via `Task` tool |
| 6 | Plugin packaging (`.claude-plugin/plugin.json` + `marketplace.json`, installable via GitHub raw URL) |
| 7 | Agent SDK CLI (`cli/ossmate`) — shares `.claude/commands/*.md` skill bodies so slash command + CLI subcommand stay in sync |
| 8 | Scheduled triggers via `CronCreate` — daily digest, weekly stale sweep, release radar (all opt-in) |
| 9 | CI/CD (3-OS × 3-Python matrix), PyPI trusted publishing via OIDC, README polish, v0.1.0 cut |

## Design rationale

**Why this order?** Earlier phases (output style, status line) produce **immediate visual feedback** — you can see the tool working within a session. This sustains motivation through the harder middle phases (MCP server, subagent orchestration) where the payoff is delayed.

**Why independently demoable?** Each phase's artifact can be shown off standalone in a portfolio or talk. Phase 2 alone is "a single slash command that triages GitHub issues" — already a complete demo. Phase 5 is "multi-agent system with model-tier routing" — another complete demo. You don't need all 10 phases to have a story.

**Why no "Phase 10"?** After Phase 9 the project enters post-v0.1.0 maintenance — new work goes into `[Unreleased]` in CHANGELOG and ships as patch/minor releases rather than large phase commits. The `ossmate doctor` subcommand (PR #3) is an example: a v0.1.x feature shipped as a regular PR, not as a new phase.

## Git tags

All ten phases are tagged. Browse:

```bash
git tag -l 'phase-*'
git checkout phase-5  # inspect repo state at end of Phase 5
```

Or see GitHub's [tags page](https://github.com/sunjin12/ossmate/tags) for tagged releases.
