"""Stop summary — append a one-line journal entry per finished session.

Writes to .ossmate/journal.md so the maintainer has a chronological record of
what each Claude session worked on. Captures:
- timestamp
- session_id (truncated)
- changed file count (`git status --porcelain | wc -l`)
- last commit subject (one line)

Never blocks. If git isn't available or the project isn't a repo, writes a
timestamp-only entry so the journal still grows.

Note: avoids re-firing when stop_hook_active=true to prevent infinite loops.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import have_git, project_dir, read_event  # noqa: E402


def main() -> None:
    event = read_event()
    if event.get("stop_hook_active"):
        return  # avoid re-entry loop

    cwd = project_dir()
    sid = (event.get("session_id") or "anon")[:8]
    ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    changed = "?"
    last_commit = ""
    if have_git() and (cwd / ".git").exists():
        try:
            porcelain = subprocess.run(
                ["git", "-C", str(cwd), "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
            ).stdout
            changed = str(sum(1 for _ in porcelain.splitlines()))
            last_commit = subprocess.run(
                ["git", "-C", str(cwd), "log", "-1", "--pretty=%s"],
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
            ).stdout.strip()
        except (subprocess.TimeoutExpired, OSError):
            pass

    entry = f"- {ts} · session `{sid}` · {changed} unstaged · last: {last_commit or '(no commit)'}\n"

    journal = cwd / ".ossmate" / "journal.md"
    journal.parent.mkdir(parents=True, exist_ok=True)
    if not journal.exists():
        journal.write_text("# Ossmate session journal\n\n", encoding="utf-8")
    with journal.open("a", encoding="utf-8") as fh:
        fh.write(entry)


if __name__ == "__main__":
    main()
