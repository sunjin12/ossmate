"""PreToolUse(Bash) guard — block destructive maintainer-side commands.

Rules (in order):
1. `git push --force` / `-f` to any branch        -> block (never)
2. `git push <remote> main`                        -> block (must use PR)
3. `git push <remote> master`                      -> block
4. `git reset --hard origin/*` while on main       -> block
5. `npm publish` / `twine upload` / `pip publish`  -> block (release flow only)
6. `gh release create`                             -> block (release flow only)
7. `gh pr merge`                                   -> block (merge via UI)
8. `gh issue close|comment|edit|lock`              -> block (skill must propose)

For any blocked command, exit 2 with stderr explaining WHY and HOW to proceed.
Claude Code feeds stderr back to the model so it can adapt.

Non-Bash tools and unmatched Bash commands fall through with exit 0.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import block, read_event  # noqa: E402

DESTRUCTIVE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\bgit\s+push\b.*\s(--force|-f)\b"),
        "Force-push is denied by Ossmate guard. Reason: rewrites shared history. "
        "If you truly need to recover, use `git push --force-with-lease` after "
        "explicit user approval.",
    ),
    (
        re.compile(r"\bgit\s+push\b.*\b(origin\s+)?(main|master)\b"),
        "Direct push to main/master is denied by Ossmate guard. "
        "Open a PR instead: `git push origin <feature-branch>` then `gh pr create`.",
    ),
    (
        re.compile(r"\bgit\s+reset\s+--hard\b"),
        "`git reset --hard` is denied by Ossmate guard while it could be on a shared branch. "
        "Use `git stash` or create a recovery branch first.",
    ),
    (
        re.compile(r"\b(npm|yarn|pnpm)\s+publish\b"),
        "Package publishing is denied through this hook. Releases must go through "
        "the `/release-notes` + CI release workflow.",
    ),
    (
        re.compile(r"\btwine\s+upload\b|\bpython\s+-m\s+twine\s+upload\b"),
        "PyPI upload via twine is denied through this hook. Use the GitHub "
        "Actions release pipeline instead (see .github/workflows/release.yml).",
    ),
    (
        re.compile(r"\bgh\s+release\s+create\b"),
        "`gh release create` is denied through this hook. Run `/release-notes <ver>` "
        "first to draft notes; the user creates the release manually after review.",
    ),
    (
        re.compile(r"\bgh\s+pr\s+merge\b"),
        "`gh pr merge` is denied. Merge through the GitHub UI after maintainer review.",
    ),
    (
        re.compile(r"\bgh\s+issue\s+(close|comment|edit|lock|reopen)\b"),
        "Issue-state mutations via gh are denied. Skills must propose the change as a "
        "comment block; the user runs the gh command themselves after review.",
    ),
    (
        re.compile(r"\bgh\s+pr\s+(comment|edit|close|reopen)\b"),
        "PR-state mutations via gh are denied. Same rule as issues — propose first, "
        "let the maintainer execute.",
    ),
]


def main() -> None:
    event = read_event()

    if event.get("tool_name") != "Bash":
        return  # exit 0

    cmd: str = (event.get("tool_input") or {}).get("command", "")
    if not cmd:
        return

    for pattern, reason in DESTRUCTIVE_PATTERNS:
        if pattern.search(cmd):
            block(f"[ossmate guard] {reason}\nCommand was: {cmd}")

    # No match -> allow
    return


if __name__ == "__main__":
    main()
