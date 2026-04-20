"""Ossmate environment diagnostics — 6 checks that self-diagnose ~80% of
first-run failures (missing `gh`, unauthed `gh`, missing `.claude/`, broken
MCP install, `.ossmate/` permission issues).

Each check is a pure `(project_root: Path | None) -> CheckResult` function so
it can be unit-tested in isolation. `run_all` composes them in a fixed order.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Literal

from .tools.repo import ProjectRootNotFoundError, find_project_root

Status = Literal["ok", "warn", "fail"]


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    detail: str
    hint: str = ""


MIN_PYTHON = (3, 11)
MCP_SELFTEST_TIMEOUT_S = 10
GH_AUTH_TIMEOUT_S = 5


def check_python(_project_root: Path | None) -> CheckResult:
    v = sys.version_info
    detail = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) >= MIN_PYTHON:
        return CheckResult("python", "ok", detail)
    return CheckResult(
        "python",
        "fail",
        detail,
        hint=f"Ossmate requires Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+",
    )


def check_ossmate(_project_root: Path | None) -> CheckResult:
    try:
        v = _pkg_version("ossmate")
    except PackageNotFoundError:
        return CheckResult(
            "ossmate",
            "fail",
            "not installed",
            hint="Install with `pipx install ossmate`",
        )
    return CheckResult("ossmate", "ok", v)


def check_gh(_project_root: Path | None) -> CheckResult:
    gh_path = shutil.which("gh")
    if gh_path is None:
        return CheckResult(
            "gh cli",
            "warn",
            "not found",
            hint=(
                "Install from https://cli.github.com/ — Ossmate falls back to "
                "PyGithub but `gh` speeds up PR/issue commands"
            ),
        )
    try:
        result = subprocess.run(
            [gh_path, "auth", "status"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=GH_AUTH_TIMEOUT_S,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return CheckResult(
            "gh cli",
            "warn",
            f"auth probe failed ({type(exc).__name__})",
            hint="Run `gh auth login` and retry",
        )
    if result.returncode == 0:
        return CheckResult("gh cli", "ok", "authenticated")
    return CheckResult(
        "gh cli",
        "warn",
        "not authenticated",
        hint="Run `gh auth login` to enable PR/issue commands",
    )


def check_mcp_server(_project_root: Path | None) -> CheckResult:
    try:
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "ossmate_mcp", "--selftest"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=MCP_SELFTEST_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            "mcp server",
            "fail",
            f"selftest timed out after {MCP_SELFTEST_TIMEOUT_S}s",
            hint="Reinstall with `pipx install ossmate-mcp`",
        )
    except OSError as exc:
        return CheckResult(
            "mcp server",
            "fail",
            f"could not spawn Python ({exc})",
            hint="Reinstall with `pipx install ossmate-mcp`",
        )
    if result.returncode != 0:
        stderr_tail = (result.stderr or "").strip().splitlines()[-1:] or [""]
        return CheckResult(
            "mcp server",
            "fail",
            f"selftest exit code {result.returncode}: {stderr_tail[0]}",
            hint="Reinstall with `pipx install ossmate-mcp`",
        )
    first_line = (result.stdout or "").strip().splitlines()[:1] or [""]
    return CheckResult("mcp server", "ok", first_line[0] or "selftest ok")


def check_project_root(project_root: Path | None) -> CheckResult:
    try:
        root = find_project_root(project_root)
    except ProjectRootNotFoundError:
        return CheckResult(
            "project root",
            "warn",
            "no `.claude/commands/` above cwd",
            hint="Run from inside a repo with `.claude/commands/`",
        )
    return CheckResult("project root", "ok", str(root))


def check_ossmate_writable(project_root: Path | None) -> CheckResult:
    try:
        root = find_project_root(project_root)
    except ProjectRootNotFoundError:
        return CheckResult(
            ".ossmate writable",
            "warn",
            "skipped — no project root",
            hint="This check runs once `project root` resolves",
        )
    artifacts = root / ".ossmate"
    probe = artifacts / ".write-probe"
    try:
        artifacts.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return CheckResult(
            ".ossmate writable",
            "fail",
            f"{artifacts}: {exc.strerror or exc}",
            hint="Check filesystem permissions on the project root",
        )
    return CheckResult(".ossmate writable", "ok", str(artifacts))


# Ordered so output reads top-down: runtime → package → external → server → repo.
_CHECKS = (
    check_python,
    check_ossmate,
    check_gh,
    check_mcp_server,
    check_project_root,
    check_ossmate_writable,
)


def run_all(project_root: Path | None) -> list[CheckResult]:
    return [c(project_root) for c in _CHECKS]


def render_pretty(results: list[CheckResult]) -> None:
    from rich.console import Console

    console = Console()
    glyph = {
        "ok": "[green]✓[/green]",
        "warn": "[yellow]⚠[/yellow]",
        "fail": "[red]✗[/red]",
    }
    for r in results:
        console.print(f"{glyph[r.status]}  {r.name:<18} {r.detail}")
        if r.hint and r.status != "ok":
            console.print(f"   [dim]→ {r.hint}[/dim]")


def render_json(results: list[CheckResult]) -> str:
    return json.dumps(
        {"checks": [asdict(r) for r in results]}, indent=2, ensure_ascii=False
    )
