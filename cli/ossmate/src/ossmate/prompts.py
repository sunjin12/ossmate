"""Skill loader: parses `.claude/commands/<name>.md` so the CLI can reuse the
exact same prompt body that Claude Code's slash commands run.

This is the core of the dual-distribution promise: one prompt, two front-ends.
Editing a `.claude/commands/*.md` file changes both the slash command and the
matching `ossmate <name>` CLI subcommand at the same time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_KV_RE = re.compile(r"^([A-Za-z][\w-]*)\s*:\s*(.*)$")
_PLACEHOLDER_RE = re.compile(r"\$(\d+|ARGUMENTS)")


class SkillNotFoundError(FileNotFoundError):
    """Raised when a slash command file is missing on disk."""


class MalformedSkillError(ValueError):
    """Raised when a skill file is missing its YAML frontmatter."""


@dataclass(frozen=True)
class Skill:
    name: str
    body: str
    description: str = ""
    model: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    argument_hint: str = ""
    source_path: Path | None = None


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Minimal YAML frontmatter parser.

    Skill frontmatter is intentionally flat (no nested blocks), so a regex split
    + line scan beats pulling PyYAML into the CLI's dependency tree.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise MalformedSkillError("missing `---` YAML frontmatter")
    raw_meta, body = match.group(1), match.group(2)
    meta: dict[str, str] = {}
    for line in raw_meta.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        kv = _KV_RE.match(line)
        if not kv:
            continue
        meta[kv.group(1)] = kv.group(2).strip()
    return meta, body


def load_skill(name: str, project_root: Path) -> Skill:
    path = project_root / ".claude" / "commands" / f"{name}.md"
    if not path.exists():
        raise SkillNotFoundError(f"skill `{name}` not found at {path}")
    meta, body = _parse_frontmatter(path.read_text(encoding="utf-8"))

    allowed = meta.get("allowed-tools", "")
    tools = [t.strip() for t in allowed.split() if t.strip()] if allowed else []

    return Skill(
        name=name,
        body=body.strip(),
        description=meta.get("description", ""),
        model=meta.get("model") or None,
        allowed_tools=tools,
        argument_hint=meta.get("argument-hint", ""),
        source_path=path,
    )


def render(skill: Skill, args: list[str]) -> str:
    """Substitute `$1`..`$N` and `$ARGUMENTS` in the skill body.

    Unlike Claude Code's substitution, missing positional args resolve to an
    empty string rather than the literal `$N` — the skills' own preamble lines
    handle the empty-arg case (most start with "If `$1` is empty, stop and ask").
    """
    arguments = " ".join(args)

    def _sub(match: re.Match[str]) -> str:
        token = match.group(1)
        if token == "ARGUMENTS":
            return arguments
        idx = int(token) - 1
        return args[idx] if 0 <= idx < len(args) else ""

    return _PLACEHOLDER_RE.sub(_sub, skill.body)
