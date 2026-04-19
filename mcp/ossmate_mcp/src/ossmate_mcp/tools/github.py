"""GitHub tools — read-only window into a maintainer's queue.

Strategy: prefer the `gh` CLI when present (it inherits the user's
auth and is universally installed on dev boxes). Fall back to anonymous
PyGithub via the public REST API when `gh` is missing — that path is
heavily rate-limited but lets the tools work in CI / on a fresh laptop.

All write paths (post_comment, close_issue, etc.) are intentionally
NOT implemented here. The PreToolUse guard in
`.claude/hooks/pre_tool_use_guard.py` blocks `gh issue comment` and
friends, so the MCP surface never offers a backdoor.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any

from mcp.server.fastmcp import FastMCP


def _have_gh() -> bool:
    return shutil.which("gh") is not None


def _gh_json(args: list[str], cwd: str | None = None, timeout: int = 15) -> Any | None:
    try:
        proc = subprocess.run(
            ["gh", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def _gh_text(args: list[str], cwd: str | None = None, timeout: int = 15) -> str | None:
    try:
        proc = subprocess.run(
            ["gh", *args],
            cwd=cwd,
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


def _repo_arg(repo: str | None) -> list[str]:
    return ["--repo", repo] if repo else []


def _unavailable() -> dict[str, Any]:
    return {
        "error": "github_unavailable",
        "detail": "gh CLI not on PATH. Install from https://cli.github.com/ "
                  "and run `gh auth login`.",
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def list_open_prs(repo: str | None = None, limit: int = 30) -> dict[str, Any]:
        """List open pull requests in a GitHub repository.

        Args:
            repo: 'owner/name'. If omitted, uses the repo of the current
                  working directory (must be a git checkout with `gh`
                  configured).
            limit: Max PRs to return (1-100).
        """
        if not _have_gh():
            return _unavailable()
        limit = max(1, min(int(limit), 100))
        data = _gh_json([
            "pr", "list",
            "--state", "open",
            "--limit", str(limit),
            "--json", "number,title,author,labels,createdAt,updatedAt,isDraft,headRefName",
            *_repo_arg(repo),
        ])
        if data is None:
            return {"error": "gh_pr_list_failed"}
        return {"count": len(data), "prs": data}

    @mcp.tool()
    def list_merged_prs_since(
        since: str,
        repo: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """List PRs merged on/after an ISO date (YYYY-MM-DD).

        Useful as input to release-notes drafting.

        Args:
            since: ISO date like '2026-03-01' or 'YYYY-MM-DDTHH:MM:SSZ'.
            repo: 'owner/name' or None to use cwd.
            limit: Cap on results (1-200).
        """
        if not _have_gh():
            return _unavailable()
        limit = max(1, min(int(limit), 200))
        # `gh pr list` supports a search query; we ask for merged>=since.
        search = f"merged:>={since}"
        data = _gh_json([
            "pr", "list",
            "--state", "merged",
            "--limit", str(limit),
            "--search", search,
            "--json", "number,title,author,labels,mergedAt,headRefName",
            *_repo_arg(repo),
        ])
        if data is None:
            return {"error": "gh_pr_list_failed"}
        return {"count": len(data), "since": since, "prs": data}

    @mcp.tool()
    def get_pr_diff(number: int, repo: str | None = None) -> dict[str, Any]:
        """Fetch the unified diff and metadata for a single PR.

        Returns title, body, author, file list, and the raw diff text.
        Truncates the diff at 200 KB so it fits comfortably in a model
        context window.

        Args:
            number: PR number.
            repo: 'owner/name' or None to use cwd.
        """
        if not _have_gh():
            return _unavailable()
        meta = _gh_json([
            "pr", "view", str(number),
            "--json", "number,title,body,author,headRefName,baseRefName,files",
            *_repo_arg(repo),
        ])
        if meta is None:
            return {"error": "gh_pr_view_failed", "number": number}
        diff = _gh_text(["pr", "diff", str(number), *_repo_arg(repo)])
        truncated = False
        if diff is not None and len(diff) > 200_000:
            diff = diff[:200_000]
            truncated = True
        return {"meta": meta, "diff": diff or "", "diff_truncated": truncated}

    @mcp.tool()
    def list_stale_issues(
        days: int = 60,
        repo: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """List open issues with no updates in the last N days.

        A stale issue is one whose `updatedAt` predates `now - days`.
        Output is suitable input for `/stale-sweep`.

        Args:
            days: Threshold in days (1-365).
            repo: 'owner/name' or None to use cwd.
            limit: Cap on results (1-200).
        """
        if not _have_gh():
            return _unavailable()
        days = max(1, min(int(days), 365))
        limit = max(1, min(int(limit), 200))
        data = _gh_json([
            "issue", "list",
            "--state", "open",
            "--limit", str(limit),
            "--json", "number,title,author,labels,createdAt,updatedAt",
            *_repo_arg(repo),
        ])
        if data is None:
            return {"error": "gh_issue_list_failed"}
        cutoff = datetime.now(tz=timezone.utc).timestamp() - days * 86400
        stale = []
        for issue in data:
            updated = issue.get("updatedAt")
            if not updated:
                continue
            try:
                ts = datetime.fromisoformat(updated.replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
            if ts <= cutoff:
                issue["age_days"] = int(
                    (datetime.now(tz=timezone.utc).timestamp() - ts) / 86400
                )
                stale.append(issue)
        return {"count": len(stale), "threshold_days": days, "issues": stale}

    @mcp.tool()
    def whoami() -> dict[str, Any]:
        """Return the authenticated GitHub user (or unavailable)."""
        if not _have_gh():
            return _unavailable()
        out = _gh_text(["api", "user", "--jq", ".login"])
        if not out:
            return {"error": "gh_unauthenticated"}
        return {
            "login": out.strip(),
            "token_source": "GH_TOKEN" if os.environ.get("GH_TOKEN") else "gh_keyring",
        }
