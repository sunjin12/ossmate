"""Shared helpers for Ossmate hook scripts.

All hook entry points read JSON from stdin and either exit 0/2 or write JSON
to stdout. This module centralizes the I/O contract so individual hooks stay
short and testable.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def read_event() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"hook: invalid stdin JSON: {e}", file=sys.stderr)
        sys.exit(1)


def emit(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.stdout.flush()


def block(reason: str) -> None:
    """PreToolUse / PostToolUse / Stop blocking exit."""
    print(reason, file=sys.stderr)
    sys.exit(2)


def project_dir() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def have_gh() -> bool:
    return _which("gh") is not None


def have_git() -> bool:
    return _which("git") is not None


def _which(name: str) -> str | None:
    from shutil import which

    return which(name)


def gh_json(args: list[str], cwd: Path | None = None, timeout: int = 8) -> Any | None:
    """Run gh with --json and return parsed result, or None on any failure."""
    if not have_gh():
        return None
    try:
        proc = subprocess.run(
            ["gh", *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
