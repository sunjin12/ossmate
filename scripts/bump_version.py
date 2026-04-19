"""Bump the Ossmate version everywhere it appears.

Ossmate's version lives in four files (two pyproject.toml manifests, plus the
plugin manifest and the self-marketplace). They MUST stay in lockstep — a stale
version in any one of them produces a confusing UX (`pip` and `claude plugin`
disagreeing on which version is installed). This script is the single
source-of-truth for bumping; `tests/test_versioning.py` enforces the lockstep.

Usage:

    python scripts/bump_version.py 0.2.0          # set explicit version
    python scripts/bump_version.py --check        # exit non-zero if files drift
    python scripts/bump_version.py --print        # print the current version

The script is intentionally dependency-free (stdlib only) so CI can call it
before installing project dependencies.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# (file, regex, replacement template). Each regex must contain exactly one
# capture group whose contents are the version literal to swap.
_PYPROJECT_RE = re.compile(r'^(version\s*=\s*")([^"]+)(")', re.MULTILINE)
_DEP_PIN_RE = re.compile(r'("ossmate-mcp\s*>=\s*)([^"]+)(")')

VERSIONED_PYPROJECTS: tuple[Path, ...] = (
    REPO_ROOT / "mcp" / "ossmate_mcp" / "pyproject.toml",
    REPO_ROOT / "cli" / "ossmate" / "pyproject.toml",
)
PLUGIN_MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE_MANIFEST = REPO_ROOT / ".claude-plugin" / "marketplace.json"

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?$")


def read_pyproject_version(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = _PYPROJECT_RE.search(text)
    if not match:
        raise ValueError(f"{path}: no top-level `version = \"...\"` line found")
    return match.group(2)


def write_pyproject_version(path: Path, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    new_text, count = _PYPROJECT_RE.subn(rf'\g<1>{new}\g<3>', text, count=1)
    if count != 1:
        raise ValueError(f"{path}: failed to update version")
    # Also update the `ossmate-mcp >= X` dep pin in the CLI's pyproject so
    # CLI and MCP advance together.
    new_text = _DEP_PIN_RE.sub(rf'\g<1>{new}\g<3>', new_text)
    path.write_text(new_text, encoding="utf-8")


def read_json_version(path: Path, key_path: tuple[str, ...]) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    cur: object = data
    for key in key_path:
        assert isinstance(cur, dict), f"{path}: expected dict at {key_path}"
        cur = cur[key]
    if not isinstance(cur, str):
        raise ValueError(f"{path}: version at {key_path} is not a string")
    return cur


def write_json_version(path: Path, key_path: tuple[str, ...], new: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    cur: dict = data
    for key in key_path[:-1]:
        cur = cur[key]
    cur[key_path[-1]] = new
    # Preserve trailing newline + 2-space indent (matches existing files).
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def collect_versions() -> dict[str, str]:
    """Return {label: version} for every place the version is recorded."""
    versions: dict[str, str] = {}
    for path in VERSIONED_PYPROJECTS:
        versions[str(path.relative_to(REPO_ROOT))] = read_pyproject_version(path)
    versions[str(PLUGIN_MANIFEST.relative_to(REPO_ROOT))] = read_json_version(
        PLUGIN_MANIFEST, ("version",)
    )
    versions[str(MARKETPLACE_MANIFEST.relative_to(REPO_ROOT)) + " (metadata)"] = (
        read_json_version(MARKETPLACE_MANIFEST, ("metadata", "version"))
    )
    data = json.loads(MARKETPLACE_MANIFEST.read_text(encoding="utf-8"))
    versions[str(MARKETPLACE_MANIFEST.relative_to(REPO_ROOT)) + " (plugins[0])"] = (
        data["plugins"][0]["version"]
    )
    return versions


def _write_marketplace_plugin_version(new: str) -> None:
    data = json.loads(MARKETPLACE_MANIFEST.read_text(encoding="utf-8"))
    data["plugins"][0]["version"] = new
    MARKETPLACE_MANIFEST.write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )


def bump(new: str) -> None:
    if not SEMVER_RE.match(new):
        raise SystemExit(f"refusing to set non-semver version: {new!r}")
    for path in VERSIONED_PYPROJECTS:
        write_pyproject_version(path, new)
    write_json_version(PLUGIN_MANIFEST, ("version",), new)
    write_json_version(MARKETPLACE_MANIFEST, ("metadata", "version"), new)
    _write_marketplace_plugin_version(new)


def check() -> int:
    versions = collect_versions()
    unique = set(versions.values())
    if len(unique) == 1:
        print(f"OK: all version markers agree on {next(iter(unique))}")
        return 0
    print("DRIFT — version markers disagree:", file=sys.stderr)
    for label, ver in versions.items():
        print(f"  {label}: {ver}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("version", nargs="?", help="new semver to set (e.g. 0.2.0)")
    group.add_argument("--check", action="store_true", help="verify all markers agree")
    group.add_argument("--print", action="store_true", help="print current version")
    args = parser.parse_args(argv)

    if args.check:
        return check()
    if args.print:
        versions = collect_versions()
        unique = set(versions.values())
        if len(unique) != 1:
            print("DRIFT", file=sys.stderr)
            return 1
        print(next(iter(unique)))
        return 0
    bump(args.version)
    print(f"bumped to {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
