"""UserPromptSubmit router — detect #N references and inject GitHub context.

Scans the user's prompt for `#1234` style references. For each (deduplicated,
max 5) it runs `gh issue view N --json title,state,labels,author,body` and
falls back to `gh pr view N` on miss. The combined results are returned as
`additionalContext` so Claude has up-to-date information without the user
copy-pasting issue bodies.

Silent if `gh` is not installed, the prompt has no #N tokens, or all lookups
fail. Never blocks the prompt.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import emit, gh_json, have_gh, project_dir, read_event  # noqa: E402

REF_RE = re.compile(r"(?<![\w/])#(\d{1,7})\b")
MAX_LOOKUPS = 5


def main() -> None:
    event = read_event()
    prompt = event.get("prompt", "")
    if not prompt or not have_gh():
        return

    refs = list(dict.fromkeys(REF_RE.findall(prompt)))[:MAX_LOOKUPS]
    if not refs:
        return

    cwd = project_dir()
    snippets: list[str] = []

    for n in refs:
        issue = gh_json(
            ["issue", "view", n, "--json", "number,title,state,labels,author,body"],
            cwd=cwd,
        )
        kind = "issue"
        if issue is None:
            issue = gh_json(
                ["pr", "view", n, "--json", "number,title,state,labels,author,body"],
                cwd=cwd,
            )
            kind = "pr"
        if issue is None:
            continue

        labels = ", ".join(lbl.get("name", "") for lbl in (issue.get("labels") or []))
        body = (issue.get("body") or "").strip()
        if len(body) > 1500:
            body = body[:1500] + "\n…(truncated)"
        snippets.append(
            f"### {kind.upper()} #{issue.get('number')}: {issue.get('title')}\n"
            f"- state: {issue.get('state')}\n"
            f"- author: @{(issue.get('author') or {}).get('login', '?')}\n"
            f"- labels: {labels or '(none)'}\n\n"
            f"{body}\n"
        )

    if not snippets:
        return

    emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": (
                    "Ossmate auto-fetched the GitHub references in your prompt:\n\n"
                    + "\n---\n".join(snippets)
                ),
            }
        }
    )


if __name__ == "__main__":
    main()
