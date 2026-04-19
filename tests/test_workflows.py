"""Phase 9 contract tests for GitHub Actions workflows.

These checks fail fast on common regressions in `.github/workflows/*.yml`:

  * a matrix entry silently dropped (Windows / macOS coverage lost)
  * pytest invocation accidentally removed
  * the release workflow forgets to verify the tag↔version match
  * publish job loses `id-token: write` (OIDC trusted publishing breaks)
  * MCP publish runs in parallel with CLI publish (CLI would install with a
    pin newer than what's on PyPI if MCP fails first)

Hermetic — string-level grammar checks, no PyYAML dependency. We deliberately
keep the parser minimal (the project's other tests use the same approach for
the scheduled-trigger frontmatter — single style across the suite).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
CI = WORKFLOWS_DIR / "ci.yml"
RELEASE = WORKFLOWS_DIR / "release.yml"


def _read(path: Path) -> str:
    assert path.exists(), f"missing workflow: {path}"
    return path.read_text(encoding="utf-8")


# ---- CI workflow -------------------------------------------------------


class TestCIWorkflow:
    def test_file_exists(self):
        assert CI.exists()

    def test_runs_on_pr_and_push_to_main(self):
        text = _read(CI)
        assert re.search(r"pull_request\s*:", text), "CI must run on PRs"
        assert re.search(r"push\s*:", text), "CI must run on pushes"
        assert "branches: [main]" in text or "branches:\n      - main" in text

    def test_three_os_matrix_present(self):
        text = _read(CI)
        for os_name in ("ubuntu-latest", "macos-latest", "windows-latest"):
            assert os_name in text, f"CI matrix missing {os_name}"

    def test_python_version_matrix(self):
        text = _read(CI)
        for v in ("3.11", "3.12", "3.13"):
            assert f'"{v}"' in text, f"CI matrix missing Python {v}"

    def test_matrix_does_not_fail_fast(self):
        """When one cell fails we want full signal across the rest."""
        text = _read(CI)
        assert "fail-fast: false" in text, (
            "fail-fast should be false so OS-specific regressions surface together"
        )

    def test_runs_pytest(self):
        text = _read(CI)
        assert re.search(r"\bpytest\b", text), "CI must invoke pytest"

    def test_verifies_version_sync(self):
        """The bump-script check is the cheapest way to catch release drift —
        if it's removed from CI a bad release can ship."""
        text = _read(CI)
        assert "bump_version.py --check" in text

    def test_concurrency_group_set(self):
        """Save CI minutes on rapid pushes."""
        assert "concurrency:" in _read(CI)

    def test_permissions_are_least_privilege(self):
        """CI should not need write permissions to anything."""
        text = _read(CI)
        # There's a top-level `permissions: contents: read`.
        assert re.search(r"permissions\s*:\s*\n\s*contents\s*:\s*read", text)


# ---- Release workflow --------------------------------------------------


class TestReleaseWorkflow:
    def test_file_exists(self):
        assert RELEASE.exists()

    def test_triggers_on_version_tag(self):
        text = _read(RELEASE)
        assert re.search(r'tags\s*:\s*\n\s*-\s*"v\*\.\*\.\*"', text), (
            "release must trigger on `v*.*.*` tags"
        )

    def test_verifies_tag_matches_version(self):
        """The most important guard in this workflow — without it, a stale tag
        could publish a mismatched version to PyPI."""
        text = _read(RELEASE)
        assert "verify-tag" in text
        assert "bump_version.py --print" in text

    def test_uses_oidc_trusted_publishing(self):
        """No long-lived API tokens in repo secrets."""
        text = _read(RELEASE)
        # Both publish jobs need id-token: write.
        assert text.count("id-token: write") >= 2, (
            "both publish-mcp and publish-cli need id-token: write for OIDC"
        )
        # And the official publishing action.
        assert "pypa/gh-action-pypi-publish" in text

    def test_publish_jobs_are_sequential_not_parallel(self):
        """publish-cli must depend on publish-mcp — CLI declares
        ossmate-mcp>=X, so if MCP publish fails, CLI install would resolve
        against an old version and break for end users."""
        text = _read(RELEASE)
        # Find the publish-cli job and confirm its `needs:` references publish-mcp.
        match = re.search(
            r"publish-cli:.*?needs\s*:\s*([^\n]+)", text, flags=re.DOTALL
        )
        assert match, "publish-cli job not found"
        needs = match.group(1)
        assert "publish-mcp" in needs, (
            "publish-cli must `needs: publish-mcp` to keep dep pin satisfiable"
        )

    def test_publish_jobs_target_pypi_environment(self):
        """The `environment: pypi` reference is what binds OIDC publishing to
        the project on PyPI's side. Drop it and trusted publishing fails."""
        text = _read(RELEASE)
        assert text.count("name: pypi") >= 2

    def test_skip_existing_set(self):
        """Lets us rerun the workflow after a transient failure without
        clobbering an already-uploaded artifact."""
        text = _read(RELEASE)
        assert text.count("skip-existing: true") >= 2


# ---- Cross-workflow invariants -----------------------------------------


class TestWorkflowDocs:
    def test_both_workflows_present(self):
        files = sorted(p.name for p in WORKFLOWS_DIR.glob("*.yml"))
        assert "ci.yml" in files
        assert "release.yml" in files
