"""Contract tests for Phase 5 Subagents and Skills.

These tests validate the YAML frontmatter of every `.claude/agents/*.md` and
`.claude/commands/*.md` file. They are hermetic — they read files only,
no network or `gh` calls.

What we enforce:

- Every subagent declares: name, description, model, tools.
- Every skill declares: description, allowed-tools, model.
- Models map to a known shorthand or full ID.
- Subagent `name` matches its filename stem (so the dispatcher can find it).
- We have exactly the planned set: 6 subagents + 8 skills.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / ".claude" / "agents"
COMMANDS_DIR = REPO_ROOT / ".claude" / "commands"

EXPECTED_AGENTS = {
    "issue-classifier",
    "community-greeter",
    "pr-triager",
    "release-notes-writer",
    "dep-auditor",
    "security-reviewer",
}

EXPECTED_SKILLS = {
    "triage-issue",
    "triage-pr",
    "release-notes",
    "stale-sweep",
    "onboard-contributor",
    "audit-deps",
    "security-review-pr",
    "changelog-bump",
}

# Model identifiers we accept in frontmatter. Shorthands per Claude Code agent
# spec, plus the full IDs the project pins for reproducibility.
KNOWN_MODELS = {
    "haiku",
    "sonnet",
    "opus",
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-7",
}


# ---- frontmatter parsing -------------------------------------------------


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """Minimal YAML frontmatter parser — only the subset our files use.

    We avoid pulling in PyYAML since the frontmatter is hand-written and
    follows a tiny grammar: scalar values, no nesting, no lists-of-maps.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    out: dict[str, Any] = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


# ---- subagent contracts --------------------------------------------------


class TestSubagents:
    def test_expected_set_present(self):
        actual = {p.stem for p in AGENTS_DIR.glob("*.md")}
        assert actual == EXPECTED_AGENTS, (
            f"unexpected agent set: missing={EXPECTED_AGENTS - actual}, "
            f"extra={actual - EXPECTED_AGENTS}"
        )

    @pytest.mark.parametrize("agent_name", sorted(EXPECTED_AGENTS))
    def test_required_frontmatter_fields(self, agent_name: str):
        path = AGENTS_DIR / f"{agent_name}.md"
        fm = _parse_frontmatter(path.read_text(encoding="utf-8"))
        for field in ("name", "description", "model", "tools"):
            assert field in fm, f"{agent_name}.md missing frontmatter field: {field}"
        assert fm["name"] == agent_name, (
            f"{agent_name}.md frontmatter name='{fm['name']}' does not match filename stem"
        )
        assert fm["model"] in KNOWN_MODELS, (
            f"{agent_name}.md uses unknown model: {fm['model']}"
        )
        # description must be useful enough for the dispatcher to route work.
        assert len(fm["description"]) >= 30, (
            f"{agent_name}.md description is suspiciously short — dispatcher needs a real hint"
        )

    def test_model_assignments(self):
        """Lock in the planned haiku/sonnet/opus matrix."""
        wanted = {
            "issue-classifier": "haiku",
            "community-greeter": "haiku",
            "pr-triager": "sonnet",
            "release-notes-writer": "sonnet",
            "dep-auditor": "sonnet",
            "security-reviewer": "opus",
        }
        for agent, expected_model in wanted.items():
            fm = _parse_frontmatter(
                (AGENTS_DIR / f"{agent}.md").read_text(encoding="utf-8")
            )
            assert fm["model"] == expected_model, (
                f"{agent} should run on {expected_model}, got {fm['model']}"
            )

    @pytest.mark.parametrize("agent_name", sorted(EXPECTED_AGENTS))
    def test_no_write_tools(self, agent_name: str):
        """Subagents must not request Write/Edit — they produce drafts, not files."""
        fm = _parse_frontmatter(
            (AGENTS_DIR / f"{agent_name}.md").read_text(encoding="utf-8")
        )
        tools = fm["tools"]
        for forbidden in ("Write", "Edit", "NotebookEdit"):
            assert forbidden not in tools, (
                f"{agent_name} requests {forbidden} — subagents must produce drafts, "
                "not mutate files"
            )

    @pytest.mark.parametrize("agent_name", sorted(EXPECTED_AGENTS))
    def test_body_present(self, agent_name: str):
        """A subagent with no system prompt body is useless."""
        text = (AGENTS_DIR / f"{agent_name}.md").read_text(encoding="utf-8")
        body = _FRONTMATTER_RE.sub("", text, count=1).strip()
        assert len(body) > 200, f"{agent_name}.md body is too short to be a real prompt"


# ---- skill contracts -----------------------------------------------------


class TestSkills:
    def test_expected_set_present(self):
        actual = {p.stem for p in COMMANDS_DIR.glob("*.md")}
        assert actual == EXPECTED_SKILLS, (
            f"unexpected skill set: missing={EXPECTED_SKILLS - actual}, "
            f"extra={actual - EXPECTED_SKILLS}"
        )

    @pytest.mark.parametrize("skill_name", sorted(EXPECTED_SKILLS))
    def test_required_frontmatter_fields(self, skill_name: str):
        path = COMMANDS_DIR / f"{skill_name}.md"
        fm = _parse_frontmatter(path.read_text(encoding="utf-8"))
        for field in ("description", "allowed-tools", "model"):
            assert field in fm, f"{skill_name}.md missing frontmatter field: {field}"
        assert fm["model"] in KNOWN_MODELS, (
            f"{skill_name}.md uses unknown model: {fm['model']}"
        )

    def test_skills_that_delegate_request_task_tool(self):
        """Skills that mention a subagent must list `Task` in allowed-tools."""
        delegating = {
            "triage-pr",
            "release-notes",
            "stale-sweep",
            "onboard-contributor",
            "audit-deps",
            "security-review-pr",
        }
        for skill in delegating:
            fm = _parse_frontmatter(
                (COMMANDS_DIR / f"{skill}.md").read_text(encoding="utf-8")
            )
            assert "Task" in fm["allowed-tools"], (
                f"{skill}.md delegates to a subagent but does not list `Task` in allowed-tools"
            )

    def test_no_destructive_gh_in_allowed_tools(self):
        """Skills must not bypass the PreToolUse hook by allow-listing mutations."""
        forbidden = (
            "gh pr merge",
            "gh pr review",
            "gh pr comment",
            "gh issue close",
            "gh issue comment",
            "gh issue edit",
            "gh release create",
            "git push --force",
            "git push -f",
        )
        for path in COMMANDS_DIR.glob("*.md"):
            fm = _parse_frontmatter(path.read_text(encoding="utf-8"))
            allowed = fm.get("allowed-tools", "")
            for verb in forbidden:
                assert verb not in allowed, (
                    f"{path.name} allow-lists destructive `{verb}` — would bypass PreToolUse hook"
                )

    @pytest.mark.parametrize("skill_name", sorted(EXPECTED_SKILLS))
    def test_skill_body_documents_workflow(self, skill_name: str):
        """A skill body should at minimum describe a workflow and a constraints section."""
        text = (COMMANDS_DIR / f"{skill_name}.md").read_text(encoding="utf-8")
        body = _FRONTMATTER_RE.sub("", text, count=1)
        assert "## Workflow" in body or "### Step" in body, (
            f"{skill_name}.md has no Workflow / Step section"
        )
        assert "## Constraints" in body or "Constraints" in body, (
            f"{skill_name}.md has no Constraints section"
        )


# ---- cross-surface invariants --------------------------------------------


class TestCrossSurface:
    def test_security_review_skill_targets_opus(self):
        """The security review surface must use the opus tier end-to-end."""
        skill_fm = _parse_frontmatter(
            (COMMANDS_DIR / "security-review-pr.md").read_text(encoding="utf-8")
        )
        agent_fm = _parse_frontmatter(
            (AGENTS_DIR / "security-reviewer.md").read_text(encoding="utf-8")
        )
        assert "opus" in skill_fm["model"]
        assert agent_fm["model"] == "opus"

    def test_cheap_triage_uses_haiku(self):
        """Bulk-classification surfaces should target haiku to keep cost down."""
        agent_fm = _parse_frontmatter(
            (AGENTS_DIR / "issue-classifier.md").read_text(encoding="utf-8")
        )
        greeter_fm = _parse_frontmatter(
            (AGENTS_DIR / "community-greeter.md").read_text(encoding="utf-8")
        )
        assert agent_fm["model"] == "haiku"
        assert greeter_fm["model"] == "haiku"
