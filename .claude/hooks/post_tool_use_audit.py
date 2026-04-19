"""PostToolUse(Bash) audit — append a JSONL record for every Bash invocation.

Output goes to ${OSSMATE_AUDIT_LOG} (defaults to .ossmate/audit.jsonl in the
project root). One line per Bash call, suitable for `jq` post-processing.

Record schema:
    {
      "ts":           "2026-04-19T12:34:56+09:00",
      "session_id":   "...",
      "tool_use_id":  "...",
      "command":      "git status",
      "exit_code":    0,
      "stdout_bytes": 123,
      "stderr_bytes": 0
    }

Never blocks (exit 0 always). Audit failures go to stderr but don't stop work.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import append_jsonl, project_dir, read_event  # noqa: E402


def main() -> None:
    event = read_event()
    if event.get("tool_name") != "Bash":
        return

    tool_input = event.get("tool_input") or {}
    tool_response = event.get("tool_response") or {}
    cmd = tool_input.get("command", "")
    if not cmd:
        return

    audit_path_env = os.environ.get("OSSMATE_AUDIT_LOG")
    audit_path = (
        Path(audit_path_env)
        if audit_path_env
        else project_dir() / ".ossmate" / "audit.jsonl"
    )

    exit_code = tool_response.get("exitCode")
    if exit_code is None:
        exit_code = tool_response.get("exit_code")

    record = {
        "ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "session_id": event.get("session_id", ""),
        "tool_use_id": event.get("tool_use_id", ""),
        "command": cmd,
        "exit_code": exit_code,
        "stdout_bytes": len(tool_response.get("stdout", "") or ""),
        "stderr_bytes": len(tool_response.get("stderr", "") or ""),
    }

    try:
        append_jsonl(audit_path, record)
    except OSError as e:
        print(f"[ossmate audit] failed to write {audit_path}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
