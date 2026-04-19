"""Shared pytest fixtures for Ossmate tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"
MCP_SRC = REPO_ROOT / "mcp" / "ossmate_mcp" / "src"

# Make the MCP package importable from tests without an editable install.
if str(MCP_SRC) not in sys.path:
    sys.path.insert(0, str(MCP_SRC))


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def hooks_dir() -> Path:
    return HOOKS_DIR


@pytest.fixture
def run_hook(tmp_path: Path):
    """Return a callable that runs a hook with given stdin JSON.

    Usage:
        result = run_hook("pre_tool_use_guard", {"tool_name": "Bash", ...})
        assert result.returncode == 2
        assert "Force-push" in result.stderr
    """

    def _run(name: str, payload: dict[str, Any], extra_env: dict[str, str] | None = None):
        script = HOOKS_DIR / f"{name}.py"
        assert script.exists(), f"missing hook script: {script}"
        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
        env["OSSMATE_AUDIT_LOG"] = str(tmp_path / "audit.jsonl")
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmp_path),
            timeout=10,
            check=False,
        )

    return _run
