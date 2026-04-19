"""Changelog tools — parse Keep-a-Changelog and propose semver bumps.

`parse` extracts the release sections from a CHANGELOG.md file written in
the Keep-a-Changelog 1.1 style. `propose_bump` reads a list of
Conventional Commits (or pulls them from git) and recommends the next
semver bump (major / minor / patch).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from packaging.version import InvalidVersion, Version

# `## [1.2.3] - 2025-01-02` or `## [Unreleased]` (date optional).
HEADING_RE = re.compile(
    r"^##\s*\[(?P<version>[^\]]+)\]"
    r"(?:\s*-\s*(?P<date>\d{4}-\d{2}-\d{2}))?"
    r"\s*$",
    re.MULTILINE,
)

# Sub-section headers inside a release: `### Added`, `### Fixed`, etc.
SUBSECTION_RE = re.compile(r"^###\s+(\w[\w \-]*)\s*$", re.MULTILINE)

# Conventional Commit subject: `<type>(<scope>)?!?: <subject>`.
CC_RE = re.compile(
    r"^(?P<type>build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test)"
    r"(?:\((?P<scope>[^)]+)\))?"
    r"(?P<bang>!)?"
    r":\s*(?P<subject>.+)$"
)

BREAKING_TRAILER_RE = re.compile(
    r"^BREAKING[ -]CHANGE:\s", re.IGNORECASE | re.MULTILINE
)


def _parse_changelog(text: str) -> list[dict[str, Any]]:
    releases: list[dict[str, Any]] = []
    headings = list(HEADING_RE.finditer(text))
    for idx, m in enumerate(headings):
        start = m.end()
        end = headings[idx + 1].start() if idx + 1 < len(headings) else len(text)
        body = text[start:end]
        # Bucket bullets by sub-section.
        buckets: dict[str, list[str]] = {}
        current = "Notes"
        for line in body.splitlines():
            sub = SUBSECTION_RE.match(line)
            if sub:
                current = sub.group(1).strip()
                buckets.setdefault(current, [])
                continue
            stripped = line.strip()
            if stripped.startswith(("- ", "* ")):
                buckets.setdefault(current, []).append(stripped[2:].strip())
        releases.append({
            "version": m.group("version"),
            "date": m.group("date"),
            "sections": buckets,
        })
    return releases


def _classify_commits(subjects: list[str]) -> dict[str, Any]:
    bump = "none"
    matched: list[dict[str, str]] = []
    unmatched: list[str] = []

    for raw in subjects:
        line = raw.strip()
        if not line:
            continue
        # The "subject" we receive may be the full commit message body, so
        # only match the first line for the type, but scan the rest for a
        # BREAKING CHANGE trailer.
        first, _, rest = line.partition("\n")
        m = CC_RE.match(first.strip())
        if not m:
            unmatched.append(first.strip())
            continue
        is_breaking = bool(m.group("bang")) or bool(BREAKING_TRAILER_RE.search(rest))
        ctype = m.group("type")
        matched.append({
            "type": ctype,
            "scope": m.group("scope") or "",
            "breaking": "true" if is_breaking else "false",
            "subject": m.group("subject"),
        })
        # Bump precedence: major > minor > patch > none.
        if is_breaking:
            bump = "major"
        elif ctype == "feat" and bump in {"none", "patch"}:
            bump = "minor"
        elif ctype in {"fix", "perf", "revert"} and bump == "none":
            bump = "patch"

    return {"bump": bump, "matched": matched, "unmatched": unmatched}


def _next_version(current: str, bump: str) -> str | None:
    if bump == "none":
        return current
    try:
        v = Version(current.lstrip("v"))
    except InvalidVersion:
        return None
    major, minor, patch = v.major, v.minor, v.micro
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return None


def _git_subjects(repo: Path, since: str | None) -> list[str] | None:
    args = ["log", "--pretty=format:%s%n%b%n---END---"]
    if since:
        args.append(f"{since}..HEAD")
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    chunks = proc.stdout.split("---END---")
    return [c.strip() for c in chunks if c.strip()]


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def parse(path: str = "CHANGELOG.md") -> dict[str, Any]:
        """Parse a Keep-a-Changelog 1.1 file into structured release data.

        Returns a list of releases, each with `version`, optional `date`,
        and `sections` (a dict from sub-section name → list of bullets).
        Use this before drafting release notes so the new entry doesn't
        duplicate existing wording.

        Args:
            path: Path to the changelog file. Resolved relative to CWD.
        """
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return {"error": f"file not found: {p}"}
        text = p.read_text(encoding="utf-8")
        releases = _parse_changelog(text)
        return {"path": str(p), "release_count": len(releases), "releases": releases}

    @mcp.tool()
    def propose_bump(
        current_version: str,
        commit_subjects: list[str] | None = None,
        repo_path: str = ".",
        since: str | None = None,
    ) -> dict[str, Any]:
        """Propose the next semver bump from Conventional Commits.

        Either pass `commit_subjects` directly (one commit message per
        item — first line is the subject, the rest may include
        'BREAKING CHANGE:' trailers) or omit it to read commits from a
        local git repository.

        Bump rules:
        - `feat!:` or 'BREAKING CHANGE:' trailer  -> major
        - `feat:`                                  -> minor (if no major)
        - `fix:` / `perf:` / `revert:`             -> patch (if no minor)
        - everything else                          -> no bump

        Args:
            current_version: Latest released version, e.g. '1.4.2' or 'v1.4.2'.
            commit_subjects: Optional explicit list. If omitted we fall
                             back to git log.
            repo_path: Repository to scan when commit_subjects is omitted.
            since: Git revision used as the lower bound, e.g. 'v1.4.2'.
                   Only used when reading from git.
        """
        subjects: list[str] | None = commit_subjects
        source = "explicit"
        if subjects is None:
            subjects = _git_subjects(Path(repo_path).expanduser().resolve(), since)
            source = "git"
            if subjects is None:
                return {"error": "git unavailable or no commits found"}
        analysis = _classify_commits(subjects)
        proposed = _next_version(current_version, analysis["bump"])
        return {
            "source": source,
            "current_version": current_version,
            "bump": analysis["bump"],
            "proposed_version": proposed,
            "matched_count": len(analysis["matched"]),
            "unmatched_count": len(analysis["unmatched"]),
            "matched": analysis["matched"],
            "unmatched": analysis["unmatched"],
        }
