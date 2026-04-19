"""Find the Ossmate project root from any working directory.

The CLI is meant to be invoked from any subdirectory of an Ossmate-managed
repo. We walk upward looking for a marker that proves we're inside one — either
the `.claude/` directory (Ossmate-managed) or a `.git/` boundary (last resort).
"""

from __future__ import annotations

from pathlib import Path


class ProjectRootNotFoundError(FileNotFoundError):
    """Raised when no `.claude/` ancestor exists from the given directory."""


def find_project_root(start: Path | None = None) -> Path:
    cur = (start or Path.cwd()).resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / ".claude" / "commands").is_dir():
            return candidate
    raise ProjectRootNotFoundError(
        f"no `.claude/commands/` directory found above {cur} — "
        "run `ossmate` from inside an Ossmate-managed repo"
    )


def mcp_server_config(project_root: Path) -> dict[str, object]:
    """Return the stdio config for the bundled ossmate MCP server.

    Mirrors `.mcp.json` but resolves `${CLAUDE_PROJECT_DIR}` to an absolute
    path so the SDK can launch the subprocess without a Claude Code env.
    """
    pythonpath = (project_root / "mcp" / "ossmate_mcp" / "src").as_posix()
    return {
        "type": "stdio",
        "command": "python",
        "args": ["-X", "utf8", "-m", "ossmate_mcp"],
        "env": {
            "PYTHONPATH": pythonpath,
            "PYTHONIOENCODING": "utf-8",
        },
    }
