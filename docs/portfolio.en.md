# Ossmate — Portfolio Retrospective

**One-liner**: An open-source CLI + Claude Code plugin that automates the repetitive work of OSS maintainers by combining all 12 Claude Code extension surfaces.

- **Repo**: [github.com/sunjin12/ossmate](https://github.com/sunjin12/ossmate)
- **Distribution**: PyPI (`ossmate`, `ossmate-mcp`), Claude Code plugin marketplace
- **Scale**: Python 3.11+, 176 tests (pytest, ~5s), 3-OS × 3-Python CI matrix, 10 phase tags
- **Duration**: Incremental self-build from Phase 0 to v0.1.0; still self-dogfooding through v0.1.x patches (PR #1~#4)
- **Solo project** (spec, design, implementation, release, maintenance — all by one person)

---

## 1. What Problem Was I Solving?

### Primary — Repetitive maintainer operations

Beyond their core work (features, reviews), solo maintainers are drained by **repetitive, attention-taxing operational chores**:

| Task | Friction without Ossmate |
|---|---|
| PR triage | Read diff / commits / CI and judge scope/risk/mergeability by hand, every PR |
| Issue classification | Manually label every incoming issue as bug/feature/docs/duplicate/… |
| Release notes | Scrape commits since the last tag and re-format into Keep-a-Changelog |
| Dependency audit | Re-assemble lockfile parsing + OSV advisory lookup every time |
| Stale-issue sweep | Find issues idle for 60+ days and decide nudge vs. close |
| Contributor onboarding | Hand-write welcome messages for each first-time contributor |

The work is **patterned but still requires judgment per case** — neither fully automatable nor efficient to do manually. A perfect niche for LLM assistance.

### Secondary — Learning the Claude Code extension surfaces

Claude Code exposes 12 extension points (Skills, Subagents, Hooks, MCP, Plugin, Agent SDK, Scheduled triggers, Status line, Output styles, Memory, Settings, Keybindings), but **there were few examples integrating all of them into a single coherent product**. To really feel what each surface contributes to a real domain, the fastest path is to build it yourself.

→ **Ossmate is designed to serve both purposes at once**: a practical tool, and a reference implementation of Claude Code.

---

## 2. How I Built It

### Design principle: 10 phases, each independently demoable

| Phase | Deliverable |
|---|---|
| 0 | Skeleton (pyproject × 2, CLAUDE.md, settings.json) |
| 1 | Output style + status line — **immediate visual feedback** |
| 2 | First Skill `/triage-issue` — Bash-only, pre-MCP |
| 3 | 5 Hooks (including PreToolUse guard) |
| 4 | MCP server — 11 tools + 3 resource templates |
| 5 | 6 Subagents (haiku/sonnet/opus tiering) + remaining skills refactored to delegate |
| 6 | Plugin packaging + self-hosted `marketplace.json` |
| 7 | Standalone CLI — reloads `.claude/commands/*.md` bodies so one skill powers both slash + subcommand |
| 8 | Scheduled triggers (daily digest, weekly stale sweep, Friday release radar) |
| 9 | CI/CD 3-OS × 3-Python matrix + OIDC PyPI publishing → v0.1.0 cut |

Each phase is tagged `phase-N`, so `git checkout phase-5` shows the snapshot at that point. **Any phase boundary is a shippable demo** — a guardrail against scope creep.

### Architecture

```
User ─┬─ /slash commands ──► Claude Code ──► Skills ──► Subagents ──► MCP ──► GitHub API
      └─ ossmate CLI ─────► Agent SDK ────────────────────────────┘          OSV.dev
                                                                              Local repo
```

**The same MCP server backs both the plugin and the standalone CLI** → tools (gh calls, OSV queries, lockfile parsing) are written once and reused everywhere.

### Why each surface

Every one of the 12 surfaces is justified by **what friction appears when it's missing** ([README.md:111-130](../README.md#L111-L130) table). Not a contrived demo mapping; each plays a real role in actual use:

- **Subagent model tiering** — Haiku for bulk issue classification, Opus for security review, Sonnet for PR triage. Cost/speed optimization vs. a one-size-fits-all model.
- **PreToolUse Hook guard** — Blocks destructive commands like `git push origin main`, `gh pr merge`, `gh release create` before they run. Later, when I tried to merge a PR myself, this hook stopped me — proving self-dogfooding works.
- **MCP vs. inline scripts** — Keeping gh/OSV/lockfile logic in MCP lets Claude Code, the CLI, and other AI clients reuse it.
- **Plugin vs. CLI** — Plugin is installable instantly for Claude Code users; CLI targets CI / remote shells / non-Claude-Code environments. A shared skill body avoids double maintenance.

---

## 3. Problems and Decisions Along the Way

### 3.1 Scope decision — "Do we really use all 12 surfaces?"

Early trade-off: Skills + MCP alone would have made a working tool. Were 12 surfaces excessive?

**Decision**: Use all surfaces — but each one must earn its place by removing a **specific friction**, not exist "for the sake of being there". Keybindings are explicitly labeled the lowest-value surface in the README table. If a surface can't be justified, it shouldn't be added.

**Why**: Portfolio value (reference implementation) + learning value (feeling each surface's real constraints) + reuse design (a shared MCP makes adding surfaces easier, not harder).

### 3.2 Plugin ↔ Standalone CLI duplication

Supporting both would normally mean duplicating slash-command bodies and CLI prompt bodies — a maintenance nightmare.

**Decision**: Treat `.claude/commands/*.md` as the single source of truth; the CLI loads markdown bodies from disk directly and feeds them to `ClaudeAgentOptions`. One skill written → slash command + CLI subcommand for free. `test_no_orphan_subcommands` enforces the invariant.

**Consequence**: When `doctor` was added in Phase 7 as CLI-only (no matching slash command), an explicit whitelist `cli_only_allowlist = {"version", "doctor"}` was added to make the exception visible.

### 3.3 Windows cp949 locale

During `doctor` implementation, `subprocess.run(text=True)` threw `UnicodeDecodeError` in cp949 locales — invisible on macOS/Linux CI.

**Decision**: Make every subprocess call pass `encoding="utf-8", errors="replace"` explicitly. Hook-script conventions are separately saved as a "Windows environment constraint" memory to avoid relearning the same lesson.

### 3.4 CI was red for 3 commits and I didn't notice

After the `phase-9` merge, `test_referenced_hook_scripts_exist` was failing on Linux/macOS but passing locally on Windows (pathlib swallowed the trailing backslash). With no notification pipeline, I pushed 3 more commits before the `doctor` PR surfaced the failure.

**Decision**:
1. Immediate fix: regex `[^\"]+` → `[^\"\\]+` (excludes trailing backslash)
2. Bundle pre-existing lint errors (24 total) into the same PR — restore green in a single bar
3. Save a memory note: "CI failure notification pipeline needed" → queued as top v0.1.x candidate

**Lesson**: A multi-OS matrix alone isn't enough — you also need a **channel that tells you when it breaks** (planning Slack webhook or badge monitoring next iteration).

### 3.5 Blocked by my own PreToolUse hook (self-dogfooding)

When merging PR #3, I tried `gh pr merge` — and the PreToolUse guard I built in Phase 3 responded: `gh pr merge is denied. Merge through the GitHub UI after maintainer review.`

**Decision**: Don't bypass. User merged via GitHub UI instead. → **Live proof that the project's security policy actually works**. Recorded in the CHANGELOG and this retrospective.

### 3.6 Scoping `ossmate doctor` (after evaluation)

Post-Phase-9 review identified "onboarding friction" as a medium-severity weakness. Three candidates:

| Candidate | Scope | Risk |
|---|---|---|
| Eval suite | Large (2~3 days) | Scope blowup |
| Hygiene bundle (templates, etc.) | Small (30 min) | Low impact |
| **`ossmate doctor`** (chosen) | Medium (2~3 hours) | Right-sized |

**Rationale**: Self-diagnoses ~80% of common failure modes (gh missing, wrong directory, broken MCP install) with a single command. Zero new dependencies (reused existing `rich`). Scope pinned at 6 checks × ≥5 tests. → Merged as PR #3.

### 3.7 Dead-link cleanup (PR #4)

A `docs/architecture.md` link existed in README, but the file didn't (user flagged it). Two other phase-doc links were pointing into memory paths (`memory/project_phases.md`) that also didn't exist.

**Decision**: Instead of creating a new file for the architecture link, inline the 12-surface justification table into README. Phase descriptions had genuine public-doc value, so materialize them at `docs/project_phases.md`. As a byproduct, relaxed the "no new markdown design docs" rule in `.claude/CLAUDE.md` to explicitly permit public explainers under `docs/`.

**Lesson**: Dead links in a public repo hit recruiter credibility directly → small docs hygiene matters as much as the implementation work.

---

## 4. Self-Assessment

### What went well

- **Scope discipline**: A 10-phase plan that actually shipped in 10 phases — no mid-flight ambition-creep before cutting v0.1.0. `[Unreleased]` convention keeps v0.1.x iterations clean.
- **Self-dogfooding**: Ossmate runs on its own repo. The hook stopped me, scheduled triggers run daily digests here, the CHANGELOG is written by Ossmate itself. Meta-consistency.
- **Test density**: 176 hermetic tests, ~5s. Rule: every new feature adds ≥5 tests. Pre-existing bugs fixed in the same PR, so CI stays green.
- **Cross-platform**: Developed on Windows, verified on Linux/macOS CI. cp949 encoding, path separators, hook execution conventions — all addressed explicitly.
- **OIDC publishing**: Zero PyPI tokens stored as secrets. Release by pushing a tag; the workflow rejects if tag version ≠ pyproject version.
- **Security policy proven in the wild**: The PreToolUse hook actually blocked my own `gh pr merge` — confirmation that the policy isn't just theater.

### What's weak

- **CI notification gap**: Main was red for 3 commits without being noticed. No badge / Slack / email pipeline yet. Top priority for next iteration.
- **Onboarding friction**: `doctor` mitigates ~80%, but users still need `pipx` + `gh auth` + MCP install. Multi-step for newcomers.
- **Zero real users yet** (besides me): Up through Phase 9 was a build cycle; it only went fully public post-v0.1.x. No adoption data yet → hard to measure real-world value.
- **Keybindings surface**: The weakest link among the 12. Honestly labeled "lowest value" in the README, but inclusion itself is worth revisiting.
- **Actions version drift** (e.g. Node.js 20 deprecation): No Dependabot config yet → manual vigilance required when the deprecation window arrives.

### What I learned

1. **Clarifying "what friction am I removing" matters more than building the tool.** Each surface's inclusion was decided by its friction-removal role rather than "I want to learn it" — and that decision drove the overall coherence.
2. **Investing in a shared data source (MCP) pays off.** Supporting both a plugin and a CLI didn't cost 2×, because both sit on the same MCP.
3. **Self-dogfooding makes bugs surface themselves.** When a hook blocks *me*, I know the policy is alive.
4. **The "independently demoable phase" principle kept scope creep in check** and also kept morale up — any phase boundary is a shippable milestone.
5. **Windows-dev + Linux-CI is not free.** Invisible-on-local failures require both a multi-OS matrix *and* a notification pipeline (the latter is still missing).
6. **Understanding the domain matters more than I thought.** Claude Code recommended the "OSS maintainer support" project for harness-programming practice, but my lack of background in actually maintaining OSS made development feel like outsourced work. Next project: build domain knowledge of the target field *first*, then start building.

### Next v0.1.x roadmap candidates

- CI failure notification pipeline (Slack webhook / email / badge audit)
- Dependabot + Node.js 20 → bump actions versions
- PR / Issue templates (under `.github/`)
- Expand `doctor` checks based on real user feedback (git-lfs, Node version, plugin marketplace sync)
- Eval suite — catch skill-output quality regressions

---

## Related docs

- [README](../README.md) — Quickstart, per-surface value
- [docs/project_phases.md](project_phases.md) — 10-phase detailed plan
- [CHANGELOG](../CHANGELOG.md) — Version history (generated by Ossmate itself)
- [CONTRIBUTING](../CONTRIBUTING.md) — Dev setup / commit conventions
