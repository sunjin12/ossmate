"""Phase 7 contract tests for the standalone CLI.

Hermetic — never starts the live SDK. We test:

  * skill loader correctly parses every `.claude/commands/*.md` file
  * `$1` / `$ARGUMENTS` substitution behaves as the slash-command spec demands
  * each Typer subcommand maps 1:1 to a real skill file
  * `--dry-run` produces a JSON plan without touching the network or SDK
  * MCP server config mirrors `.mcp.json` so the CLI's in-process server is
    exactly the one the plugin/project use
  * project-root discovery walks upward through nested cwd to find `.claude/`
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ossmate import cli as cli_module
from ossmate.agent import RunRequest, run
from ossmate.prompts import (
    MalformedSkillError,
    SkillNotFoundError,
    Skill,
    load_skill,
    render,
)
from ossmate.tools.repo import (
    ProjectRootNotFoundError,
    find_project_root,
    mcp_server_config,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMANDS_DIR = REPO_ROOT / ".claude" / "commands"


# ---- prompts.py ---------------------------------------------------------


class TestSkillLoader:
    def test_loads_every_real_skill(self):
        files = sorted(COMMANDS_DIR.glob("*.md"))
        assert files, ".claude/commands/ unexpectedly empty"
        for path in files:
            skill = load_skill(path.stem, REPO_ROOT)
            assert skill.name == path.stem
            assert skill.body, f"{path.stem} body is empty after frontmatter strip"
            assert skill.description, f"{path.stem} missing description in frontmatter"
            assert skill.model, f"{path.stem} missing model — required for CLI dispatch"

    def test_missing_skill_raises(self):
        with pytest.raises(SkillNotFoundError):
            load_skill("does-not-exist", REPO_ROOT)

    def test_malformed_frontmatter_raises(self, tmp_path: Path):
        broken = tmp_path / ".claude" / "commands" / "broken.md"
        broken.parent.mkdir(parents=True)
        broken.write_text("no frontmatter here\nbody only\n", encoding="utf-8")
        with pytest.raises(MalformedSkillError):
            load_skill("broken", tmp_path)

    def test_allowed_tools_parsed_into_list(self):
        skill = load_skill("triage-pr", REPO_ROOT)
        joined = " ".join(skill.allowed_tools)
        assert "Bash(gh pr view:*)" in joined
        assert "Task" in skill.allowed_tools


class TestPlaceholderRendering:
    def test_substitutes_positional_args(self):
        skill = Skill(name="t", body="run $1 then $2 done")
        assert render(skill, ["alpha", "beta"]) == "run alpha then beta done"

    def test_substitutes_arguments_token(self):
        skill = Skill(name="t", body="raw=[$ARGUMENTS]")
        assert render(skill, ["--days", "30"]) == "raw=[--days 30]"

    def test_missing_positional_arg_resolves_to_empty(self):
        """The slash-command spec says missing $N becomes empty so the skill's
        own preamble (`If $1 is empty, stop and ask`) handles it."""
        skill = Skill(name="t", body="hello $1!")
        assert render(skill, []) == "hello !"

    def test_no_substitution_when_no_placeholder(self):
        skill = Skill(name="t", body="static body, nothing to substitute")
        assert render(skill, ["x"]) == "static body, nothing to substitute"


# ---- tools/repo.py ------------------------------------------------------


class TestProjectRootDiscovery:
    def test_finds_root_from_repo(self):
        assert find_project_root(REPO_ROOT) == REPO_ROOT

    def test_finds_root_from_nested_subdir(self):
        nested = REPO_ROOT / "cli" / "ossmate" / "src" / "ossmate"
        assert find_project_root(nested) == REPO_ROOT

    def test_raises_when_no_claude_dir(self, tmp_path: Path):
        with pytest.raises(ProjectRootNotFoundError):
            find_project_root(tmp_path)

    def test_mcp_server_config_mirrors_project_mcp_json(self):
        cfg = mcp_server_config(REPO_ROOT)
        project_mcp = json.loads((REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))
        ref = project_mcp["mcpServers"]["ossmate"]

        assert cfg["type"] == ref["type"]
        assert cfg["command"] == ref["command"]
        assert cfg["args"] == ref["args"]
        # Project version templates the path; CLI resolves it. Both must point
        # to the same on-disk source tree.
        assert cfg["env"]["PYTHONPATH"].endswith("mcp/ossmate_mcp/src")
        assert cfg["env"]["PYTHONIOENCODING"] == "utf-8"
        assert Path(cfg["env"]["PYTHONPATH"]).exists()


# ---- agent.py (dry-run mode, no SDK call) -------------------------------


class TestDryRun:
    def test_dry_run_returns_json_plan(self, capsys):
        skill = load_skill("triage-pr", REPO_ROOT)
        code = run(
            RunRequest(
                skill=skill,
                args=["1234"],
                project_root=REPO_ROOT,
                dry_run=True,
            )
        )
        assert code == 0
        captured = capsys.readouterr()
        plan = json.loads(captured.out)
        assert plan["skill"] == "triage-pr"
        assert plan["args"] == ["1234"]
        assert plan["options"]["model"] == skill.model
        assert "ossmate" in plan["options"]["mcp_servers"]
        # Rendered prompt must show $1 was substituted.
        assert "1234" in plan["rendered_prompt_preview"]

    def test_dry_run_honors_model_override(self, capsys):
        skill = load_skill("triage-issue", REPO_ROOT)
        code = run(
            RunRequest(
                skill=skill,
                args=["42"],
                project_root=REPO_ROOT,
                dry_run=True,
                model_override="claude-haiku-4-5-20251001",
            )
        )
        assert code == 0
        plan = json.loads(capsys.readouterr().out)
        assert plan["options"]["model"] == "claude-haiku-4-5-20251001"


# ---- cli.py subcommand <-> skill mapping --------------------------------

# These tests don't *invoke* Typer — they just assert that for every skill on
# disk, a matching CLI subcommand exists, and vice versa. This catches the
# common drift where someone adds a new skill but forgets to expose it.


def _registered_subcommands() -> set[str]:
    """Pull the registered command names directly from the Typer app."""
    typer = pytest.importorskip("typer")  # noqa: F841
    return {info.name for info in cli_module.app.registered_commands if info.name}


class TestCliSkillMapping:
    def test_every_skill_has_a_subcommand(self):
        skill_names = {p.stem for p in COMMANDS_DIR.glob("*.md")}
        registered = _registered_subcommands()
        missing = skill_names - registered
        assert not missing, (
            f"these skills have no CLI subcommand: {sorted(missing)} — "
            f"add a `@app.command(\"<name>\")` in cli.py"
        )

    def test_no_orphan_subcommands(self):
        """A subcommand without a matching skill file is dead code."""
        skill_names = {p.stem for p in COMMANDS_DIR.glob("*.md")}
        # `version` is the one CLI-only command we expect.
        cli_only_allowlist = {"version"}
        registered = _registered_subcommands() - cli_only_allowlist
        orphans = registered - skill_names
        assert not orphans, (
            f"these CLI subcommands have no matching skill: {sorted(orphans)}"
        )

    def test_subcommand_names_are_kebab_case(self):
        kebab = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
        for name in _registered_subcommands():
            assert kebab.match(name), f"subcommand `{name}` is not kebab-case"


# ---- end-to-end through Typer's CliRunner -------------------------------


class TestTyperEndToEnd:
    """Real Typer dispatch with --dry-run to prove argument plumbing works."""

    def test_help_lists_all_subcommands(self):
        typer_testing = pytest.importorskip("typer.testing")
        runner = typer_testing.CliRunner()
        result = runner.invoke(cli_module.app, ["--help"])
        assert result.exit_code == 0
        for skill_name in (p.stem for p in COMMANDS_DIR.glob("*.md")):
            assert skill_name in result.output, (
                f"`{skill_name}` not in --help output — Typer didn't register it"
            )

    def test_triage_pr_dry_run_through_typer(self):
        typer_testing = pytest.importorskip("typer.testing")
        runner = typer_testing.CliRunner()
        result = runner.invoke(
            cli_module.app,
            ["triage-pr", "999", "--dry-run", "--cwd", str(REPO_ROOT)],
        )
        assert result.exit_code == 0, result.output
        plan = json.loads(result.output)
        assert plan["skill"] == "triage-pr"
        assert plan["args"] == ["999"]

    def test_stale_sweep_flags_propagate(self):
        typer_testing = pytest.importorskip("typer.testing")
        runner = typer_testing.CliRunner()
        result = runner.invoke(
            cli_module.app,
            ["stale-sweep", "--days", "30", "--label", "bug",
             "--dry-run", "--cwd", str(REPO_ROOT)],
        )
        assert result.exit_code == 0, result.output
        plan = json.loads(result.output)
        # Flags must end up in the rendered prompt via $ARGUMENTS substitution
        # — the skill body says `Parse $ARGUMENTS for --days <N>`.
        assert "--days 30" in plan["rendered_prompt_preview"]
        assert "--label bug" in plan["rendered_prompt_preview"]

    def test_version_command(self):
        typer_testing = pytest.importorskip("typer.testing")
        runner = typer_testing.CliRunner()
        result = runner.invoke(cli_module.app, ["version"])
        assert result.exit_code == 0
        assert result.output.startswith("ossmate ")
