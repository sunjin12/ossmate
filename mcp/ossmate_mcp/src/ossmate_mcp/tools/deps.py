"""Dependency tools — read lockfiles, query OSV for known advisories.

`read_lockfile` auto-detects the ecosystem (npm / pnpm / yarn / poetry /
pip-tools / cargo) and returns a normalized list of `{name, version,
ecosystem}` records. `check_advisories` posts a batched query to
osv.dev and returns matching advisories.

Network hits go through `httpx` with a short timeout. Failures degrade
gracefully — the tool returns an `error` key so the caller (skill or
subagent) can decide whether to escalate or continue.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_QUERY_URL = "https://api.osv.dev/v1/query"

# Map our short ecosystem names to OSV's canonical names.
OSV_ECOSYSTEM = {
    "npm": "npm",
    "pypi": "PyPI",
    "cargo": "crates.io",
}


def _read_package_lock(path: Path) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[dict[str, str]] = []
    # npm v7+: `packages` keyed by path, root is "".
    packages = data.get("packages") or {}
    for key, info in packages.items():
        if not key or not isinstance(info, dict):
            continue
        # Normalize: "node_modules/lodash" -> "lodash".
        name = key.split("node_modules/", 1)[-1]
        version = info.get("version")
        if name and version:
            out.append({"name": name, "version": version, "ecosystem": "npm"})
    # Fallback for older v1 lockfiles.
    if not out and "dependencies" in data:
        for name, info in (data.get("dependencies") or {}).items():
            v = info.get("version") if isinstance(info, dict) else None
            if name and v:
                out.append({"name": name, "version": v, "ecosystem": "npm"})
    return out


def _read_poetry_lock(path: Path) -> list[dict[str, str]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    out = []
    for pkg in data.get("package", []) or []:
        name = pkg.get("name")
        version = pkg.get("version")
        if name and version:
            out.append({"name": name, "version": version, "ecosystem": "pypi"})
    return out


def _read_uv_lock(path: Path) -> list[dict[str, str]]:
    return _read_poetry_lock(path)  # Same `[[package]]` schema in uv.lock.


def _read_cargo_lock(path: Path) -> list[dict[str, str]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    out = []
    for pkg in data.get("package", []) or []:
        name = pkg.get("name")
        version = pkg.get("version")
        if name and version:
            out.append({"name": name, "version": version, "ecosystem": "cargo"})
    return out


# Ordered: most specific lockfile first.
LOCKFILE_HANDLERS: list[tuple[str, Any]] = [
    ("package-lock.json", _read_package_lock),
    ("npm-shrinkwrap.json", _read_package_lock),
    ("poetry.lock", _read_poetry_lock),
    ("uv.lock", _read_uv_lock),
    ("Cargo.lock", _read_cargo_lock),
]


def _find_lockfiles(root: Path) -> list[Path]:
    found: list[Path] = []
    for name, _ in LOCKFILE_HANDLERS:
        p = root / name
        if p.exists():
            found.append(p)
    return found


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def read_lockfile(path: str = ".") -> dict[str, Any]:
        """Auto-detect and parse a lockfile in `path`.

        Supports: package-lock.json (npm), npm-shrinkwrap.json,
        poetry.lock, uv.lock, Cargo.lock. If multiple lockfiles exist
        (polyglot repo) all are parsed and the combined list is returned.

        Args:
            path: Directory to scan. Lockfiles must be at the top level.
        """
        root = Path(path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            return {"error": f"not a directory: {root}"}
        lockfiles = _find_lockfiles(root)
        if not lockfiles:
            return {
                "root": str(root),
                "found": [],
                "packages": [],
                "note": "no recognized lockfile",
            }
        all_pkgs: list[dict[str, str]] = []
        used: list[str] = []
        for lock in lockfiles:
            handler = next(h for n, h in LOCKFILE_HANDLERS if n == lock.name)
            try:
                pkgs = handler(lock)
            except (json.JSONDecodeError, OSError, ValueError) as e:
                return {"error": f"failed to parse {lock.name}: {e}"}
            used.append(lock.name)
            all_pkgs.extend(pkgs)
        return {
            "root": str(root),
            "found": used,
            "package_count": len(all_pkgs),
            "packages": all_pkgs,
        }

    @mcp.tool()
    def check_advisories(
        packages: list[dict[str, str]],
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        """Query osv.dev for known advisories on a list of packages.

        Each input record must have `name`, `version`, and `ecosystem`
        ('npm', 'pypi', or 'cargo' — case-insensitive). Returns the
        subset of packages with at least one advisory.

        Args:
            packages: Records produced by `read_lockfile` (or hand-built).
            timeout: HTTP timeout in seconds.
        """
        # Translate to OSV's batched query shape.
        queries: list[dict[str, Any]] = []
        index: list[dict[str, str]] = []
        for pkg in packages:
            eco_in = (pkg.get("ecosystem") or "").lower()
            eco = OSV_ECOSYSTEM.get(eco_in)
            name = pkg.get("name")
            version = pkg.get("version")
            if not (eco and name and version):
                continue
            queries.append({
                "version": version,
                "package": {"name": name, "ecosystem": eco},
            })
            index.append({"name": name, "version": version, "ecosystem": eco_in})
        if not queries:
            return {"queried": 0, "vulnerable": []}

        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(OSV_BATCH_URL, json={"queries": queries})
                resp.raise_for_status()
                results = resp.json().get("results", [])
        except httpx.HTTPError as e:
            return {"error": f"osv_request_failed: {e}"}

        vulnerable: list[dict[str, Any]] = []
        for pkg, result in zip(index, results, strict=False):
            ids = [v.get("id") for v in (result.get("vulns") or [])]
            if ids:
                vulnerable.append({
                    "name": pkg["name"],
                    "version": pkg["version"],
                    "ecosystem": pkg["ecosystem"],
                    "advisory_ids": [i for i in ids if i],
                })
        return {
            "queried": len(queries),
            "vulnerable_count": len(vulnerable),
            "vulnerable": vulnerable,
        }


# ---- module-level smoke helper (debugging) --------------------------------

def _smoke() -> int:
    """Quick stdout dump — for `python -m ossmate_mcp.tools.deps`."""
    here = Path(__file__).resolve().parents[4]
    print(json.dumps({"root": str(here), "found": _find_lockfiles(here)},
                     default=str, indent=2), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(_smoke())
