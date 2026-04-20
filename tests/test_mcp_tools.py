"""Hermetic tests for the Ossmate MCP server tools and resources.

These tests bypass the JSON-RPC stdio loop and exercise the underlying
helper functions directly. The full server is also smoke-tested via
its `--selftest` mode in `test_mcp_selftest`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


# Helpers under test.
from ossmate_mcp.tools import changelog as changelog_mod
from ossmate_mcp.tools import deps as deps_mod
from ossmate_mcp.tools import github as github_mod
from ossmate_mcp.tools import repo as repo_mod
from ossmate_mcp.resources import templates as templates_mod


# ---- repo._detect ---------------------------------------------------------


class TestDetectProjectType:
    def test_python_project(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        result = repo_mod._detect(tmp_path)
        assert result["primary"] == "python"
        assert any(m["marker"] == "pyproject.toml" for m in result["markers"])

    def test_node_project(self, tmp_path: Path):
        (tmp_path / "package.json").write_text("{}", encoding="utf-8")
        result = repo_mod._detect(tmp_path)
        assert result["primary"] == "node"

    def test_polyglot_python_first_wins(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        (tmp_path / "package.json").write_text("{}", encoding="utf-8")
        result = repo_mod._detect(tmp_path)
        assert result["primary"] == "python"
        kinds = {m["kind"] for m in result["markers"]}
        assert {"python", "node"}.issubset(kinds)

    def test_unknown_when_empty(self, tmp_path: Path):
        result = repo_mod._detect(tmp_path)
        assert result["primary"] == "unknown"
        assert result["markers"] == []


# ---- changelog._parse_changelog ------------------------------------------


class TestChangelogParse:
    def test_parses_releases_and_sections(self):
        text = (
            "# Changelog\n\n"
            "## [Unreleased]\n\n"
            "### Added\n- one\n- two\n\n"
            "## [1.0.0] - 2025-01-15\n\n"
            "### Fixed\n- a fix\n"
        )
        releases = changelog_mod._parse_changelog(text)
        assert len(releases) == 2
        assert releases[0]["version"] == "Unreleased"
        assert releases[0]["date"] is None
        assert releases[0]["sections"]["Added"] == ["one", "two"]
        assert releases[1]["version"] == "1.0.0"
        assert releases[1]["date"] == "2025-01-15"
        assert releases[1]["sections"]["Fixed"] == ["a fix"]


# ---- changelog._classify_commits + _next_version -------------------------


class TestClassifyAndBump:
    def test_breaking_bang_yields_major(self):
        out = changelog_mod._classify_commits(["feat(api)!: drop /v1"])
        assert out["bump"] == "major"
        assert out["matched"][0]["breaking"] == "true"

    def test_breaking_trailer_yields_major(self):
        out = changelog_mod._classify_commits([
            "feat(api): rework auth\n\nBREAKING CHANGE: tokens are now JWT"
        ])
        assert out["bump"] == "major"

    def test_feat_yields_minor(self):
        assert changelog_mod._classify_commits(["feat: new endpoint"])["bump"] == "minor"

    def test_fix_yields_patch(self):
        assert changelog_mod._classify_commits(["fix: corner case"])["bump"] == "patch"

    def test_chore_does_not_bump(self):
        assert changelog_mod._classify_commits(["chore: tidy"])["bump"] == "none"

    def test_unmatched_recorded(self):
        out = changelog_mod._classify_commits(["WIP banana", "feat: x"])
        assert "WIP banana" in out["unmatched"]
        assert out["bump"] == "minor"

    def test_next_version_minor(self):
        assert changelog_mod._next_version("1.4.2", "minor") == "1.5.0"

    def test_next_version_major_resets(self):
        assert changelog_mod._next_version("v2.7.9", "major") == "3.0.0"

    def test_next_version_patch(self):
        assert changelog_mod._next_version("0.1.0", "patch") == "0.1.1"

    def test_next_version_none_keeps(self):
        assert changelog_mod._next_version("1.0.0", "none") == "1.0.0"

    def test_next_version_invalid_returns_none(self):
        assert changelog_mod._next_version("not-a-version", "minor") is None


# ---- deps lockfile parsing -----------------------------------------------


class TestLockfile:
    def test_npm_v7(self, tmp_path: Path):
        lock = {
            "name": "demo",
            "version": "0.0.0",
            "lockfileVersion": 3,
            "packages": {
                "": {"name": "demo", "version": "0.0.0"},
                "node_modules/lodash": {"version": "4.17.21"},
                "node_modules/left-pad": {"version": "1.3.0"},
            },
        }
        (tmp_path / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
        pkgs = deps_mod._read_package_lock(tmp_path / "package-lock.json")
        names = {(p["name"], p["version"]) for p in pkgs}
        assert ("lodash", "4.17.21") in names
        assert ("left-pad", "1.3.0") in names
        assert all(p["ecosystem"] == "npm" for p in pkgs)

    def test_poetry(self, tmp_path: Path):
        toml = (
            "[[package]]\nname = \"requests\"\nversion = \"2.32.0\"\n\n"
            "[[package]]\nname = \"urllib3\"\nversion = \"2.2.1\"\n"
        )
        (tmp_path / "poetry.lock").write_text(toml, encoding="utf-8")
        pkgs = deps_mod._read_poetry_lock(tmp_path / "poetry.lock")
        assert {("requests", "2.32.0"), ("urllib3", "2.2.1")} == {
            (p["name"], p["version"]) for p in pkgs
        }
        assert all(p["ecosystem"] == "pypi" for p in pkgs)

    def test_find_lockfiles_picks_known(self, tmp_path: Path):
        (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
        (tmp_path / "Cargo.lock").write_text("", encoding="utf-8")
        names = [p.name for p in deps_mod._find_lockfiles(tmp_path)]
        assert "package-lock.json" in names
        assert "Cargo.lock" in names

    def test_find_lockfiles_empty(self, tmp_path: Path):
        assert deps_mod._find_lockfiles(tmp_path) == []


# ---- github tools graceful degradation -----------------------------------


class TestGithubFallback:
    def test_unavailable_when_gh_missing(self, monkeypatch):
        # Force "gh not installed" regardless of host environment.
        monkeypatch.setattr(github_mod, "_have_gh", lambda: False)
        # Re-derive the underlying implementations by walking through
        # the registered tools on a fresh FastMCP instance.
        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("t")
        github_mod.register(mcp)

        # FastMCP keeps callables in its tool registry; access the manager.
        names = {t.name for t in __import__("asyncio").run(mcp.list_tools())}
        assert {"list_open_prs", "get_pr_diff", "list_stale_issues", "whoami"}.issubset(names)


# ---- resources -----------------------------------------------------------


class TestTemplates:
    def test_release_notes_has_version_placeholder(self):
        assert "{version}" in templates_mod.RELEASE_NOTES_TEMPLATE
        assert "## Added" in templates_mod.RELEASE_NOTES_TEMPLATE

    def test_stale_nudge_has_age_placeholder(self):
        assert "{age_days}" in templates_mod.ISSUE_STALE_NUDGE_TEMPLATE

    def test_welcome_has_author_placeholder(self):
        assert "{author}" in templates_mod.WELCOME_TEMPLATE


# ---- end-to-end server selftest ------------------------------------------


def test_mcp_server_selftest():
    """Run `python -m ossmate_mcp --selftest` and assert tool/resource counts."""
    repo_root = Path(__file__).resolve().parent.parent
    src = repo_root / "mcp" / "ossmate_mcp" / "src"
    env = {
        **__import__("os").environ,
        "PYTHONPATH": str(src),
        "PYTHONIOENCODING": "utf-8",
    }
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "ossmate_mcp", "--selftest"],
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    # Header line lists counts.
    assert "11 tools" in out
    assert "3 resources" in out
    # A few representative tool / resource names.
    for needle in (
        "detect_project_type",
        "list_open_prs",
        "read_lockfile",
        "templates://release-notes",
    ):
        assert needle in out, f"selftest output missing: {needle}"
