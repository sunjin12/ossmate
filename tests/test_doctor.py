"""Phase 10 contract tests for `ossmate doctor`.

Hermetic — each check function is a pure `(project_root) -> CheckResult`, so
tests exercise them directly with `monkeypatch`/`tmp_path` instead of spawning
a real subprocess (except `test_mcp_selftest_check_ok_via_subprocess`, which
intentionally spawns `python -m ossmate_mcp --selftest` to prove end-to-end
reachability).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ossmate import cli as cli_module
from ossmate import diagnostics as diag

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestCheckPython:
    def test_passes_on_311_plus(self):
        r = diag.check_python(None)
        assert r.status == "ok"
        assert r.name == "python"
        assert sys.version.split()[0].startswith(r.detail)


class TestCheckGhCli:
    def test_warns_when_absent(self, monkeypatch):
        monkeypatch.setattr(diag.shutil, "which", lambda _: None)
        r = diag.check_gh(None)
        assert r.status == "warn"
        assert "not found" in r.detail
        assert "cli.github.com" in r.hint

    def test_warns_when_present_but_unauthed(self, monkeypatch):
        monkeypatch.setattr(diag.shutil, "which", lambda _: "/fake/gh")

        def fake_run(*_a, **_kw):
            return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="not logged in")

        monkeypatch.setattr(diag.subprocess, "run", fake_run)
        r = diag.check_gh(None)
        assert r.status == "warn"
        assert "not authenticated" in r.detail
        assert "gh auth login" in r.hint

    def test_ok_when_authed(self, monkeypatch):
        monkeypatch.setattr(diag.shutil, "which", lambda _: "/fake/gh")

        def fake_run(*_a, **_kw):
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        monkeypatch.setattr(diag.subprocess, "run", fake_run)
        r = diag.check_gh(None)
        assert r.status == "ok"


class TestCheckMcpServer:
    def test_ok_via_subprocess(self):
        """Actually spawn `python -m ossmate_mcp --selftest` — integration-style."""
        r = diag.check_mcp_server(None)
        assert r.status == "ok", f"selftest failed: {r.detail}"
        assert "tool" in r.detail.lower() or r.detail == "selftest ok"

    def test_fail_on_timeout(self, monkeypatch):
        def boom(*_a, **_kw):
            raise subprocess.TimeoutExpired(cmd="python", timeout=diag.MCP_SELFTEST_TIMEOUT_S)

        monkeypatch.setattr(diag.subprocess, "run", boom)
        r = diag.check_mcp_server(None)
        assert r.status == "fail"
        assert "timed out" in r.detail


class TestCheckProjectRoot:
    def test_ok_in_repo(self):
        r = diag.check_project_root(REPO_ROOT)
        assert r.status == "ok"
        assert Path(r.detail).resolve() == REPO_ROOT.resolve()

    def test_warns_outside_repo(self, tmp_path: Path):
        r = diag.check_project_root(tmp_path)
        assert r.status == "warn"
        assert ".claude/commands" in r.detail


class TestCheckOssmateWritable:
    def test_creates_dir_under_repo_root(self, tmp_path: Path):
        # Fake a project root: drop a `.claude/commands/` marker inside tmp_path.
        (tmp_path / ".claude" / "commands").mkdir(parents=True)
        r = diag.check_ossmate_writable(tmp_path)
        assert r.status == "ok"
        assert (tmp_path / ".ossmate").is_dir()
        assert not (tmp_path / ".ossmate" / ".write-probe").exists(), "probe file was not cleaned up"

    def test_warns_when_no_project_root(self, tmp_path: Path):
        r = diag.check_ossmate_writable(tmp_path)
        assert r.status == "warn"
        assert "skipped" in r.detail


class TestRunAll:
    def test_returns_six_results_in_fixed_order(self):
        results = diag.run_all(REPO_ROOT)
        assert [r.name for r in results] == [
            "python",
            "ossmate",
            "gh cli",
            "mcp server",
            "project root",
            ".ossmate writable",
        ]


class TestRenderJson:
    def test_schema_round_trips(self):
        results = diag.run_all(REPO_ROOT)
        payload = json.loads(diag.render_json(results))
        assert "checks" in payload
        assert len(payload["checks"]) == 6
        for entry in payload["checks"]:
            assert set(entry.keys()) == {"name", "status", "detail", "hint"}
            assert entry["status"] in {"ok", "warn", "fail"}


class TestDoctorCli:
    def test_help_lists_doctor(self):
        typer_testing = pytest.importorskip("typer.testing")
        runner = typer_testing.CliRunner()
        result = runner.invoke(cli_module.app, ["doctor", "--help"])
        assert result.exit_code == 0
        assert "diagnostic checks" in result.output.lower()
        assert "--json" in result.output

    def test_json_output_schema_via_clirunner(self):
        typer_testing = pytest.importorskip("typer.testing")
        runner = typer_testing.CliRunner()
        result = runner.invoke(
            cli_module.app,
            ["doctor", "--json", "--cwd", str(REPO_ROOT)],
        )
        # exit_code may be 0 or 1 depending on `gh` presence; both are valid here.
        assert result.exit_code in (0, 1), result.output
        payload = json.loads(result.output)
        assert len(payload["checks"]) == 6

    def test_exits_zero_in_this_repo_except_for_gh(self):
        """Core success criterion: everything but `gh cli` must pass in CI."""
        typer_testing = pytest.importorskip("typer.testing")
        runner = typer_testing.CliRunner()
        result = runner.invoke(
            cli_module.app,
            ["doctor", "--json", "--cwd", str(REPO_ROOT)],
        )
        payload = json.loads(result.output)
        fails = [c for c in payload["checks"] if c["status"] == "fail"]
        assert not fails, (
            f"hard checks failed in repo CI: {fails} — "
            "python / ossmate / mcp server / .ossmate writable must all pass"
        )
        # gh may or may not be installed, but everything else must be `ok`.
        for c in payload["checks"]:
            if c["name"] == "gh cli":
                continue
            assert c["status"] == "ok", (
                f"expected `{c['name']}` to be ok in this repo, got {c['status']}: {c['detail']}"
            )
