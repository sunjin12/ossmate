"""Contract tests for Phase 6 Plugin packaging.

Validates `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
plus the plugin-context twins (`hooks.json`, `mcp.json`) that swap
`${CLAUDE_PROJECT_DIR}` for `${CLAUDE_PLUGIN_ROOT}` so the bundle works
when installed in a foreign repo.

Hermetic — JSON parse only, no install attempt, no network.

What we enforce:

- plugin.json is valid JSON, has required `name`, name is kebab-case.
- All component paths in plugin.json point at things that actually exist.
- marketplace.json is valid JSON with required name/owner/plugins.
- The marketplace plugin entry name matches plugin.json name (so the
  install URL `ossmate@ossmate` resolves).
- hooks.json mirrors the project hooks but with `${CLAUDE_PLUGIN_ROOT}`,
  not `${CLAUDE_PROJECT_DIR}` — otherwise the plugin breaks once installed.
- mcp.json mirrors `.mcp.json` with the same root swap.
- All five hook events from settings.json are also wired in plugin hooks.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_DIR = REPO_ROOT / ".claude-plugin"
PLUGIN_MANIFEST = PLUGIN_DIR / "plugin.json"
MARKETPLACE = PLUGIN_DIR / "marketplace.json"
PLUGIN_HOOKS = PLUGIN_DIR / "hooks.json"
PLUGIN_MCP = PLUGIN_DIR / "mcp.json"

PROJECT_SETTINGS = REPO_ROOT / ".claude" / "settings.json"
PROJECT_MCP = REPO_ROOT / ".mcp.json"

KEBAB_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---- plugin.json ---------------------------------------------------------


class TestPluginManifest:
    def test_exists_and_parses(self):
        assert PLUGIN_MANIFEST.exists(), "plugin.json missing"
        data = _load_json(PLUGIN_MANIFEST)
        assert isinstance(data, dict)

    def test_required_fields(self):
        data = _load_json(PLUGIN_MANIFEST)
        assert "name" in data, "plugin.json must declare `name`"
        assert KEBAB_RE.match(data["name"]), (
            f"plugin name `{data['name']}` is not kebab-case"
        )
        assert data["name"] == "ossmate", (
            "plugin name must stay `ossmate` — it anchors the install URL `ossmate@ossmate`"
        )

    def test_metadata_present(self):
        """Optional in spec, but required for a portfolio-quality plugin."""
        data = _load_json(PLUGIN_MANIFEST)
        for field in ("version", "description", "author", "license", "repository"):
            assert field in data, f"plugin.json missing `{field}` — needed for marketplace listing"
        assert re.match(r"^\d+\.\d+\.\d+", data["version"]), (
            f"version `{data['version']}` is not semver"
        )

    def test_component_paths_resolve(self):
        """If you point at a directory, that directory must exist."""
        data = _load_json(PLUGIN_MANIFEST)
        for key in ("commands", "agents", "outputStyles", "hooks", "mcpServers"):
            value = data.get(key)
            if not value or not isinstance(value, str):
                continue
            rel = value[2:] if value.startswith("./") else value
            target = (REPO_ROOT / rel).resolve()
            assert target.exists(), (
                f"plugin.json `{key}: {value}` points to nonexistent path {target}"
            )


# ---- marketplace.json ----------------------------------------------------


class TestMarketplaceManifest:
    def test_exists_and_parses(self):
        assert MARKETPLACE.exists(), "marketplace.json missing"
        data = _load_json(MARKETPLACE)
        assert isinstance(data, dict)

    def test_required_fields(self):
        data = _load_json(MARKETPLACE)
        for field in ("name", "owner", "plugins"):
            assert field in data, f"marketplace.json missing `{field}`"
        assert KEBAB_RE.match(data["name"]), (
            f"marketplace name `{data['name']}` is not kebab-case"
        )
        assert "name" in data["owner"], "marketplace owner must include name"
        assert isinstance(data["plugins"], list) and data["plugins"], (
            "marketplace.json must list at least one plugin"
        )

    def test_install_url_resolves(self):
        """`claude plugin install ossmate@ossmate` resolves plugin@marketplace.

        The plugin entry's `name` must match plugin.json's `name`, otherwise
        the install URL in the README is broken.
        """
        marketplace = _load_json(MARKETPLACE)
        plugin = _load_json(PLUGIN_MANIFEST)
        listed = [p["name"] for p in marketplace["plugins"]]
        assert plugin["name"] in listed, (
            f"plugin `{plugin['name']}` is not listed in marketplace.json plugins[]"
        )

    def test_plugin_source_uses_github(self):
        """Self-hosted on GitHub — the source must be a github descriptor."""
        data = _load_json(MARKETPLACE)
        entry = next(p for p in data["plugins"] if p["name"] == "ossmate")
        source = entry["source"]
        assert isinstance(source, dict), (
            "source must be a structured descriptor for reproducibility, not a bare path"
        )
        assert source.get("source") == "github", (
            f"source kind should be 'github', got {source.get('source')!r}"
        )
        assert source.get("repo") == "sunjin12/ossmate", (
            f"source repo should be `sunjin12/ossmate`, got {source.get('repo')!r}"
        )


# ---- plugin hooks.json (the ${CLAUDE_PLUGIN_ROOT} twin) ------------------


class TestPluginHooks:
    def test_exists_and_parses(self):
        assert PLUGIN_HOOKS.exists(), ".claude-plugin/hooks.json missing"
        data = _load_json(PLUGIN_HOOKS)
        assert "hooks" in data, "plugin hooks.json must wrap events under `hooks`"

    def test_all_five_events_wired(self):
        """The plugin must register the same five events as the project."""
        plugin_hooks = _load_json(PLUGIN_HOOKS)["hooks"]
        project_hooks = _load_json(PROJECT_SETTINGS)["hooks"]
        assert set(plugin_hooks.keys()) == set(project_hooks.keys()), (
            "plugin hooks.json events differ from project settings.json — "
            "behavior would diverge once installed"
        )

    def test_uses_plugin_root_not_project_dir(self):
        """If a plugin hook command references CLAUDE_PROJECT_DIR it breaks
        the moment the plugin is installed in someone else's repo."""
        text = PLUGIN_HOOKS.read_text(encoding="utf-8")
        assert "${CLAUDE_PROJECT_DIR}" not in text, (
            "plugin hooks.json must not reference CLAUDE_PROJECT_DIR — "
            "use CLAUDE_PLUGIN_ROOT so paths resolve under the install cache"
        )
        assert "${CLAUDE_PLUGIN_ROOT}" in text, (
            "plugin hooks.json should resolve script paths via CLAUDE_PLUGIN_ROOT"
        )

    def test_referenced_hook_scripts_exist(self):
        """A typo in a path silently disables the hook — prevent that."""
        text = PLUGIN_HOOKS.read_text(encoding="utf-8")
        # Exclude both `"` and `\` from the capture: the JSON-escaped `\"`
        # that terminates the command string otherwise leaves a trailing `\`
        # on Linux/macOS where pathlib treats it as a literal filename char.
        for match in re.finditer(r"\$\{CLAUDE_PLUGIN_ROOT\}([^\"\\]+)", text):
            rel = match.group(1).lstrip("/")
            target = REPO_ROOT / rel
            assert target.exists(), (
                f"plugin hook references nonexistent script: {rel}"
            )


# ---- plugin mcp.json (the ${CLAUDE_PLUGIN_ROOT} twin) --------------------


class TestPluginMcp:
    def test_exists_and_parses(self):
        assert PLUGIN_MCP.exists(), ".claude-plugin/mcp.json missing"
        data = _load_json(PLUGIN_MCP)
        assert "mcpServers" in data
        assert "ossmate" in data["mcpServers"], (
            "plugin mcp.json must register the `ossmate` server under the same key as .mcp.json"
        )

    def test_uses_plugin_root_not_project_dir(self):
        text = PLUGIN_MCP.read_text(encoding="utf-8")
        assert "${CLAUDE_PROJECT_DIR}" not in text, (
            "plugin mcp.json must not reference CLAUDE_PROJECT_DIR"
        )
        assert "${CLAUDE_PLUGIN_ROOT}" in text, (
            "plugin mcp.json should reach the bundled MCP source via CLAUDE_PLUGIN_ROOT"
        )

    def test_command_invocation_matches_project(self):
        """The plugin MCP server should invoke ossmate_mcp the same way as
        the project's `.mcp.json` — same module, same flags."""
        plugin = _load_json(PLUGIN_MCP)["mcpServers"]["ossmate"]
        project = _load_json(PROJECT_MCP)["mcpServers"]["ossmate"]
        assert plugin["command"] == project["command"]
        assert plugin["args"] == project["args"]
        assert plugin["type"] == project["type"]
