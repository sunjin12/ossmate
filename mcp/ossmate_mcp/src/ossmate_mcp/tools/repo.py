"""Repository-introspection tools — detect project type, recent commits.

These tools are pure-local: they touch the filesystem and shell out to git
but never reach the network. They form the safest tier of the MCP surface
and are useful as smoke tests when wiring the server into a new client.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

# Markers in priority order. The first match wins so we report a primary
# language even in polyglot repos (e.g., a Python project that also ships
# a small Node toolchain).
PROJECT_MARKERS: list[tuple[str, str, str]] = [
    ("python", "pyproject.toml", "PEP 621 / Poetry / Hatch project"),
    ("python", "setup.py", "legacy setuptools project"),
    ("python", "requirements.txt", "pip requirements file"),
    ("node", "package.json", "Node.js / npm / pnpm / yarn project"),
    ("rust", "Cargo.toml", "Cargo workspace or crate"),
    ("go", "go.mod", "Go module"),
    ("ruby", "Gemfile", "Bundler project"),
    ("java-maven", "pom.xml", "Maven project"),
    ("java-gradle", "build.gradle", "Gradle project"),
    ("java-gradle", "build.gradle.kts", "Gradle (Kotlin DSL) project"),
    ("dotnet", "*.csproj", "C# / .NET project"),
]


def _detect(root: Path) -> dict[str, Any]:
    found: list[dict[str, str]] = []
    primary: str | None = None
    for kind, pattern, note in PROJECT_MARKERS:
        if "*" in pattern:
            matches = sorted(root.glob(pattern))
        else:
            p = root / pattern
            matches = [p] if p.exists() else []
        for match in matches:
            entry = {"kind": kind, "marker": match.name, "note": note}
            found.append(entry)
            if primary is None:
                primary = kind
    return {
        "root": str(root),
        "primary": primary or "unknown",
        "markers": found,
    }


def _run_git(args: list[str], cwd: Path, timeout: int = 8) -> str | None:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def detect_project_type(path: str = ".") -> dict[str, Any]:
        """Inspect a directory and identify the project type by marker files.

        Returns the primary kind (python, node, rust, go, ruby, java-maven,
        java-gradle, dotnet, or 'unknown') plus every marker found. Useful
        as a first step before deciding which lockfile reader or test
        runner to invoke.

        Args:
            path: Directory to inspect. Defaults to the current working
                  directory of the MCP server process.
        """
        root = Path(path).expanduser().resolve()
        if not root.exists():
            return {"error": f"path does not exist: {root}"}
        if not root.is_dir():
            return {"error": f"not a directory: {root}"}
        return _detect(root)

    @mcp.tool()
    def list_recent_commits(
        path: str = ".",
        limit: int = 20,
        since: str | None = None,
    ) -> dict[str, Any]:
        """List recent git commits in a repository.

        Args:
            path: Path inside a git working tree. Defaults to '.'.
            limit: Maximum number of commits to return (1-200).
            since: Optional git revision range like 'v1.2.0..HEAD' or a
                   date like '7.days.ago'. When set, `limit` still applies
                   on top of the range.
        """
        root = Path(path).expanduser().resolve()
        limit = max(1, min(int(limit), 200))
        sep = "\x1f"  # ASCII unit separator — unlikely in commit messages
        fmt = sep.join(["%H", "%h", "%an", "%ae", "%aI", "%s"])
        args = ["log", f"--pretty=format:{fmt}", f"-n{limit}"]
        if since:
            args.append(since)
        out = _run_git(args, root)
        if out is None:
            return {"error": "git unavailable or not a repository", "root": str(root)}
        commits: list[dict[str, str]] = []
        for line in out.splitlines():
            parts = line.split(sep)
            if len(parts) != 6:
                continue
            sha, short, name, email, when, subject = parts
            commits.append({
                "sha": sha,
                "short_sha": short,
                "author": name,
                "email": email,
                "date": when,
                "subject": subject,
            })
        return {"root": str(root), "count": len(commits), "commits": commits}
