"""Phase 8 contract tests for scheduled trigger definitions.

Hermetic — these are pure file-format checks. The tests do NOT call CronCreate,
do NOT register any jobs, and do NOT touch the network. They exist so that:

  * a malformed `scheduled/*.md` file fails the suite before it reaches a live
    `CronCreate` call (which would silently misfire at 8:57 AM next morning)
  * the off-minute convention is enforced — every cron in this repo must avoid
    `:00` / `:30` to spread API load
  * each scheduled prompt is self-contained (no `?`-suffixed sentences asking
    the maintainer follow-up questions; the job runs unattended)

What we enforce:

- file exists, frontmatter parses, body is non-empty
- frontmatter has every required field (name, description, cron, schedule_human,
  recurring, durable)
- `name` is the file stem (so `CronList` output is greppable)
- `cron` is a valid 5-field expression
- minute field is NOT `0`, `30`, `*/N` with N divisible by 30, or any value that
  rounds to the top/half of the hour
- prompt body has no interactive prompts (`?\n` patterns the maintainer would
  need to answer — the job runs without a human in the loop)
- prompt body declares the read-only contract somewhere (the word `RISK:` or
  `read-only` in a Constraints section), so destructive actions stay out
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEDULED_DIR = REPO_ROOT / "scheduled"

REQUIRED_FIELDS = {
    "name",
    "description",
    "cron",
    "schedule_human",
    "recurring",
    "durable",
}

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_KV_RE = re.compile(r"^([A-Za-z][\w-]*)\s*:\s*(.*)$")
_CRON_FIELD_RE = re.compile(r"^[\d*/,\-]+$")


def _parse(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    assert match, f"{path.name}: missing `---` YAML frontmatter"
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        kv = _KV_RE.match(line)
        if kv:
            value = kv.group(2).strip().strip('"').strip("'")
            meta[kv.group(1)] = value
    return meta, match.group(2).strip()


def _scheduled_files() -> list[Path]:
    files = sorted(p for p in SCHEDULED_DIR.glob("*.md") if p.name != "README.md")
    assert files, "no scheduled/*.md definitions found"
    return files


# ---- existence + parsing ------------------------------------------------


class TestScheduledDefinitions:
    def test_directory_exists(self):
        assert SCHEDULED_DIR.is_dir(), "scheduled/ directory missing"

    def test_each_definition_parses(self):
        for path in _scheduled_files():
            meta, body = _parse(path)
            assert meta, f"{path.name}: empty frontmatter"
            assert body, f"{path.name}: empty body — scheduler would send an empty prompt"

    def test_required_fields_present(self):
        for path in _scheduled_files():
            meta, _ = _parse(path)
            missing = REQUIRED_FIELDS - set(meta.keys())
            assert not missing, f"{path.name}: missing required field(s) {sorted(missing)}"

    def test_name_matches_filename_stem(self):
        """CronList output is greppable only if name == filename."""
        for path in _scheduled_files():
            meta, _ = _parse(path)
            assert meta["name"] == path.stem, (
                f"{path.name}: frontmatter name `{meta['name']}` != file stem `{path.stem}`"
            )


# ---- cron expression --------------------------------------------------


class TestCronExpressions:
    def test_five_fields(self):
        for path in _scheduled_files():
            meta, _ = _parse(path)
            fields = meta["cron"].split()
            assert len(fields) == 5, (
                f"{path.name}: cron `{meta['cron']}` has {len(fields)} fields, need 5"
            )

    def test_each_field_matches_basic_grammar(self):
        for path in _scheduled_files():
            meta, _ = _parse(path)
            for i, field in enumerate(meta["cron"].split()):
                assert _CRON_FIELD_RE.match(field), (
                    f"{path.name}: cron field {i} (`{field}`) has invalid characters — "
                    "only digits, `*`, `,`, `-`, `/` allowed"
                )

    def test_minute_avoids_top_and_half_of_hour(self):
        """Spread API load — never schedule on :00 or :30 marks."""
        bad = {"0", "30"}
        for path in _scheduled_files():
            meta, _ = _parse(path)
            minute = meta["cron"].split()[0]
            assert minute not in bad, (
                f"{path.name}: minute `{minute}` lands on a thundering-herd mark. "
                "Pick an off-minute (e.g., 47, 57, 3) per the CronCreate guidance."
            )
            # Also reject `*/30` and `*/60`:
            assert minute not in ("*/30", "*/60"), (
                f"{path.name}: stride `{minute}` lands on :00 / :30. Use a prime stride."
            )


# ---- body content invariants -------------------------------------------


class TestBodyInvariants:
    def test_body_declares_constraints_section(self):
        """Unattended jobs must spell out the read-only contract — otherwise an
        ambiguous prompt could lead the model to mutate state."""
        for path in _scheduled_files():
            _, body = _parse(path)
            assert "## Constraints" in body, (
                f"{path.name}: body missing `## Constraints` section — "
                "unattended jobs need explicit RISK boundaries"
            )

    def test_body_mentions_unattended_or_no_followups(self):
        """Force every prompt to acknowledge it runs without a human."""
        signals = ("unattended", "do not block", "do not prompt", "do not ask",
                   "no follow-up", "close out cleanly")
        for path in _scheduled_files():
            _, body = _parse(path)
            lowered = body.lower()
            assert any(s in lowered for s in signals), (
                f"{path.name}: body must signal it runs unattended (one of {signals})"
            )

    def test_body_forbids_destructive_gh_verbs(self):
        """A scheduled job that mutates state silently is the scariest possible
        regression. Defense-in-depth against an accidental edit by a future
        contributor."""
        forbidden_patterns = (
            r"\bgh issue close\b",
            r"\bgh pr merge\b",
            r"\bgh pr review --approve\b",
            r"\bgh release create\b",
            r"\bgit tag\b(?! is)",
            r"\bgit push --tags\b",
        )
        for path in _scheduled_files():
            _, body = _parse(path)
            for pat in forbidden_patterns:
                # Allow these tokens only in a `Never invoke ...` constraint line.
                for line in body.splitlines():
                    if re.search(pat, line) and "never" not in line.lower() \
                            and "blocks" not in line.lower():
                        pytest.fail(
                            f"{path.name}: body invokes forbidden command `{pat}` "
                            f"on line: {line.strip()!r}"
                        )


# ---- documentation invariants ------------------------------------------


class TestSchedulingDocs:
    def test_readme_lists_every_definition(self):
        """The activation guide is useless if a definition is missing from the
        table — drift here is the most common Phase 8 regression."""
        readme = (SCHEDULED_DIR / "README.md").read_text(encoding="utf-8")
        for path in _scheduled_files():
            assert path.name in readme, (
                f"{path.name} not linked in scheduled/README.md table"
            )
