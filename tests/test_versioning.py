"""Phase 9 contract tests for version synchronization across release artifacts.

The Ossmate version is recorded in 5 places:

  1. mcp/ossmate_mcp/pyproject.toml      [project.version]
  2. cli/ossmate/pyproject.toml          [project.version]
  3. cli/ossmate/pyproject.toml          [project.dependencies] -- "ossmate-mcp>=X"
  4. .claude-plugin/plugin.json          .version
  5. .claude-plugin/marketplace.json     .metadata.version  AND  .plugins[0].version

If any one of these drifts, end users see a confusing UX: pip says one version,
`/plugin info` says another, marketplace listings advertise a third. The
release workflow's `verify-tag` job ALSO compares the git tag against the
pyproject version, so drift here would block release.

These tests are hermetic — they only read files and import the bump script.
They don't run pip, don't touch the network, and don't mutate any file.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
BUMP_SCRIPT = SCRIPTS_DIR / "bump_version.py"


def _load_bump_module():
    """Import scripts/bump_version.py without requiring scripts/ to be a package."""
    spec = importlib.util.spec_from_file_location("ossmate_bump_version", BUMP_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bump():
    return _load_bump_module()


# ---- script existence + invocability -----------------------------------


class TestBumpScript:
    def test_script_exists(self):
        assert BUMP_SCRIPT.exists(), "scripts/bump_version.py missing"

    def test_script_is_importable(self, bump):
        assert hasattr(bump, "collect_versions")
        assert hasattr(bump, "bump")
        assert hasattr(bump, "check")

    def test_semver_regex_rejects_garbage(self, bump):
        """The bump script must refuse non-semver versions to keep PyPI happy."""
        import argparse

        with pytest.raises(SystemExit):
            bump.bump("v1.2.3")  # leading v
        with pytest.raises(SystemExit):
            bump.bump("1.2")  # missing patch
        with pytest.raises(SystemExit):
            bump.bump("latest")


# ---- the central invariant ---------------------------------------------


class TestVersionSync:
    def test_all_version_markers_agree(self, bump):
        versions = bump.collect_versions()
        unique = set(versions.values())
        assert len(unique) == 1, (
            f"version drift across {len(versions)} markers: {versions}"
        )

    def test_check_subcommand_returns_zero_in_a_clean_repo(self, bump):
        """`bump_version.py --check` must succeed at HEAD — Phase 9 release
        gate depends on it."""
        rc = bump.check()
        assert rc == 0, "bump_version.py --check failed at HEAD — fix drift"


# ---- per-file version readers (lock the file shape) -------------------


class TestVersionedFilesShape:
    def test_pyproject_files_exist(self):
        assert (REPO_ROOT / "mcp" / "ossmate_mcp" / "pyproject.toml").exists()
        assert (REPO_ROOT / "cli" / "ossmate" / "pyproject.toml").exists()

    def test_plugin_manifest_has_version_key(self):
        data = json.loads(
            (REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        assert "version" in data
        assert isinstance(data["version"], str)

    def test_marketplace_manifest_has_two_version_locations(self):
        """The bump script writes BOTH `.metadata.version` and
        `.plugins[0].version` — if the schema changes, both readers must
        be updated together."""
        data = json.loads(
            (REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )
        assert "metadata" in data and "version" in data["metadata"]
        assert data["plugins"] and "version" in data["plugins"][0]

    def test_init_modules_dont_hardcode_versions(self):
        """`__init__.py` files MUST resolve __version__ from importlib.metadata
        rather than hardcoding the literal — otherwise `bump_version.py`
        misses them and `ossmate version` lies to users (regression caught
        in v0.1.0 post-release)."""
        for init in (
            REPO_ROOT / "cli" / "ossmate" / "src" / "ossmate" / "__init__.py",
            REPO_ROOT / "mcp" / "ossmate_mcp" / "src" / "ossmate_mcp" / "__init__.py",
        ):
            text = init.read_text(encoding="utf-8")
            assert "importlib.metadata" in text, (
                f"{init.relative_to(REPO_ROOT)} must read __version__ from "
                f"importlib.metadata — hardcoding drifts on every release"
            )
            # Belt-and-suspenders: forbid the literal `__version__ = "X.Y.Z"` form.
            import re as _re

            assert not _re.search(r'^__version__\s*=\s*"\d', text, _re.MULTILINE), (
                f"{init.relative_to(REPO_ROOT)} hardcodes __version__ — use "
                f"importlib.metadata.version() instead"
            )

    def test_cli_dep_pin_matches_mcp_version(self, bump):
        """The CLI declares `ossmate-mcp>=X` — X must equal the MCP package
        version, otherwise users get an unsolvable resolver state on first
        release where the pin is newer than what's on PyPI."""
        cli_text = (REPO_ROOT / "cli" / "ossmate" / "pyproject.toml").read_text(
            encoding="utf-8"
        )
        # Parse the dep pin out of the file the same way the bump script does.
        match = bump._DEP_PIN_RE.search(cli_text)
        assert match, "cli/ossmate/pyproject.toml: no `ossmate-mcp>=...` pin found"
        pinned = match.group(2)
        mcp_ver = bump.read_pyproject_version(
            REPO_ROOT / "mcp" / "ossmate_mcp" / "pyproject.toml"
        )
        assert pinned == mcp_ver, (
            f"CLI pins ossmate-mcp>={pinned} but MCP package is {mcp_ver}"
        )
