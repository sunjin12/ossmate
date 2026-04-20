# Contributing to Ossmate

Thanks for your interest! Ossmate is built in public, in phases — see [docs/project_phases.md](docs/project_phases.md).

## Development setup

```bash
git clone https://github.com/sunjin12/ossmate.git
cd ossmate
pip install -e ./mcp/ossmate_mcp[dev] -e ./cli/ossmate[dev]
pytest
```

## Code style

- Python: `ruff format` + `ruff check`
- Type-checked with `mypy`
- All hook scripts must be invoked as `python -X utf8 -m ossmate.hooks.<name>` (no shebangs, no `.sh` for hooks — Windows compatibility)

## Commit convention

Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:` …). The `/changelog-bump` skill parses these to update [CHANGELOG.md](CHANGELOG.md).

## Phase workflow

When completing a phase:
1. `git tag phase-N`
2. Update [README.md](README.md) "Built surfaces" table (`[ ]` → `[x]`)
3. Add `[Unreleased]` entries to CHANGELOG.md
