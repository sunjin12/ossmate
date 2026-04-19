"""Hook contract tests — feed each hook a JSON payload and assert behavior.

Verifies the stdin/stdout/exit-code contract for every hook in
.claude/hooks/. These tests are intentionally hermetic: they don't depend on
gh, git, or network.
"""

from __future__ import annotations

import json
from pathlib import Path


# ---------- pre_tool_use_guard ---------------------------------------------


class TestPreToolUseGuard:
    def test_allows_safe_bash(self, run_hook):
        r = run_hook("pre_tool_use_guard", {"tool_name": "Bash", "tool_input": {"command": "git status"}})
        assert r.returncode == 0, r.stderr
        assert r.stderr == ""

    def test_allows_non_bash(self, run_hook):
        r = run_hook("pre_tool_use_guard", {"tool_name": "Edit", "tool_input": {"file_path": "x"}})
        assert r.returncode == 0

    def test_blocks_push_to_main(self, run_hook):
        r = run_hook(
            "pre_tool_use_guard",
            {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}},
        )
        assert r.returncode == 2
        assert "main/master" in r.stderr

    def test_blocks_force_push(self, run_hook):
        r = run_hook(
            "pre_tool_use_guard",
            {"tool_name": "Bash", "tool_input": {"command": "git push --force origin feat"}},
        )
        assert r.returncode == 2
        assert "Force-push" in r.stderr

    def test_blocks_npm_publish(self, run_hook):
        r = run_hook(
            "pre_tool_use_guard",
            {"tool_name": "Bash", "tool_input": {"command": "npm publish"}},
        )
        assert r.returncode == 2
        assert "publishing" in r.stderr.lower()

    def test_blocks_twine_upload(self, run_hook):
        r = run_hook(
            "pre_tool_use_guard",
            {"tool_name": "Bash", "tool_input": {"command": "twine upload dist/*"}},
        )
        assert r.returncode == 2

    def test_blocks_gh_release_create(self, run_hook):
        r = run_hook(
            "pre_tool_use_guard",
            {"tool_name": "Bash", "tool_input": {"command": "gh release create v1.0.0"}},
        )
        assert r.returncode == 2

    def test_blocks_gh_pr_merge(self, run_hook):
        r = run_hook(
            "pre_tool_use_guard",
            {"tool_name": "Bash", "tool_input": {"command": "gh pr merge 42 --squash"}},
        )
        assert r.returncode == 2

    def test_blocks_gh_issue_close(self, run_hook):
        r = run_hook(
            "pre_tool_use_guard",
            {"tool_name": "Bash", "tool_input": {"command": "gh issue close 1234"}},
        )
        assert r.returncode == 2

    def test_does_not_block_gh_issue_view(self, run_hook):
        r = run_hook(
            "pre_tool_use_guard",
            {"tool_name": "Bash", "tool_input": {"command": "gh issue view 1234"}},
        )
        assert r.returncode == 0


# ---------- post_tool_use_audit --------------------------------------------


class TestPostToolUseAudit:
    def test_appends_jsonl_record(self, run_hook, tmp_path: Path):
        r = run_hook(
            "post_tool_use_audit",
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git status"},
                "tool_response": {"exitCode": 0, "stdout": "ok", "stderr": ""},
                "session_id": "abc",
                "tool_use_id": "tu1",
            },
        )
        assert r.returncode == 0
        log = tmp_path / "audit.jsonl"
        assert log.exists()
        lines = log.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["command"] == "git status"
        assert rec["exit_code"] == 0  # critical: 0 must NOT be coerced to None
        assert rec["session_id"] == "abc"
        assert "ts" in rec

    def test_skips_non_bash(self, run_hook, tmp_path: Path):
        r = run_hook(
            "post_tool_use_audit",
            {"tool_name": "Edit", "tool_input": {"file_path": "x"}, "tool_response": {}},
        )
        assert r.returncode == 0
        assert not (tmp_path / "audit.jsonl").exists()


# ---------- user_prompt_router ---------------------------------------------


class TestUserPromptRouter:
    def test_silent_on_no_refs(self, run_hook):
        r = run_hook("user_prompt_router", {"prompt": "just say hello"})
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_silent_when_gh_missing(self, run_hook):
        # gh is not installed in test env -> hook should exit silently
        r = run_hook("user_prompt_router", {"prompt": "see #123 and #456"})
        assert r.returncode == 0
        assert r.stdout.strip() == ""


# ---------- session_start_brief --------------------------------------------


class TestSessionStartBrief:
    def test_skips_clear(self, run_hook):
        r = run_hook("session_start_brief", {"source": "clear"})
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_skips_compact(self, run_hook):
        r = run_hook("session_start_brief", {"source": "compact"})
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_runs_on_startup(self, run_hook):
        # No git/gh in tmp_path -> no bullets -> silent. We just check it doesn't crash.
        r = run_hook("session_start_brief", {"source": "startup"})
        assert r.returncode == 0


# ---------- stop_summary ---------------------------------------------------


class TestStopSummary:
    def test_appends_journal(self, run_hook, tmp_path: Path):
        r = run_hook("stop_summary", {"session_id": "abc12345xyz", "stop_hook_active": False})
        assert r.returncode == 0
        journal = tmp_path / ".ossmate" / "journal.md"
        assert journal.exists()
        text = journal.read_text(encoding="utf-8")
        assert "session `abc12345`" in text  # truncated to 8 chars
        assert text.startswith("# Ossmate session journal")

    def test_skips_when_stop_hook_active(self, run_hook, tmp_path: Path):
        r = run_hook("stop_summary", {"session_id": "x", "stop_hook_active": True})
        assert r.returncode == 0
        assert not (tmp_path / ".ossmate" / "journal.md").exists()


# ---------- malformed input ------------------------------------------------


class TestMalformed:
    def test_pre_guard_handles_empty_stdin(self, run_hook):
        r = run_hook("pre_tool_use_guard", {})
        assert r.returncode == 0  # no tool_name -> falls through

    def test_post_audit_handles_empty_response(self, run_hook):
        r = run_hook(
            "post_tool_use_audit",
            {"tool_name": "Bash", "tool_input": {"command": "x"}, "tool_response": {}},
        )
        assert r.returncode == 0
