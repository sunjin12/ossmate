"""SessionStart brief — inject "today's OSS briefing" at session start.

Fires only on `source in {"startup", "resume"}` (skips `clear` and `compact`
to avoid spamming Claude after a context reset).

Tries cheap, read-only gh queries:
- count of open PRs
- count of issues opened in the last 24h
- count of issues with no activity in 60+ days (stale candidates)
- last release tag (from git)

If none of these succeed (no gh, no repo, offline) the hook silently exits 0
and produces no additionalContext.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import emit, gh_json, have_gh, have_git, project_dir, read_event  # noqa: E402


def main() -> None:
    event = read_event()
    source = event.get("source", "")
    if source not in {"startup", "resume"}:
        return

    cwd = project_dir()
    bullets: list[str] = []

    if have_gh():
        open_prs = gh_json(["pr", "list", "--state", "open", "--json", "number"], cwd=cwd)
        if isinstance(open_prs, list):
            bullets.append(f"- Open PRs: **{len(open_prs)}**")

        recent = gh_json(
            ["issue", "list", "--state", "open", "--search", "created:>=2026-04-12", "--json", "number"],
            cwd=cwd,
        )
        if isinstance(recent, list):
            bullets.append(f"- Issues opened in the last 7 days: **{len(recent)}**")

        stale = gh_json(
            ["issue", "list", "--state", "open", "--search", "updated:<2026-02-19", "--json", "number"],
            cwd=cwd,
        )
        if isinstance(stale, list):
            bullets.append(f"- Stale candidates (no activity 60d+): **{len(stale)}**")

    if have_git():
        try:
            last_tag = subprocess.run(
                ["git", "-C", str(cwd), "describe", "--tags", "--abbrev=0"],
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
            ).stdout.strip()
            if last_tag:
                bullets.append(f"- Last release tag: **{last_tag}**")
        except (subprocess.TimeoutExpired, OSError):
            pass

    if not bullets:
        return

    additional = (
        "## Ossmate session brief\n\n"
        + "\n".join(bullets)
        + "\n\nUse `/triage-pr`, `/triage-issue`, `/stale-sweep`, or `/release-notes` "
        "to act on any of the above."
    )

    emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": additional,
            }
        }
    )


if __name__ == "__main__":
    main()
