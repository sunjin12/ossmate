#!/usr/bin/env bash
# dev_link.sh — prepare a local development environment for Ossmate.
#
# Installs both Ossmate packages in editable mode into the current Python
# environment so code edits take effect immediately. Intentionally does NOT
# create or activate a venv — that's the developer's choice (pyenv/venv/uv/
# hatch all work). Run it inside whatever env you want Ossmate attached to.
#
# Usage:
#   ./scripts/dev_link.sh          # install editable, dev extras on both
#   ./scripts/dev_link.sh --mcp    # install only the MCP package
#
# Windows PowerShell equivalent: scripts/dev_link.ps1

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

only_mcp=0
only_cli=0
for arg in "$@"; do
  case "$arg" in
    --mcp) only_mcp=1 ;;
    --cli) only_cli=1 ;;
    -h|--help)
      sed -n '1,20p' "$0"
      exit 0
      ;;
    *)
      echo "unknown flag: $arg" >&2
      exit 1
      ;;
  esac
done

python -c 'import sys; print(f"dev_link: using Python {sys.version.split()[0]} at {sys.executable}")'

if [ "$only_cli" = "0" ]; then
  echo ">>> installing ossmate-mcp (editable)"
  python -m pip install -e "./mcp/ossmate_mcp[dev]"
fi

if [ "$only_mcp" = "0" ]; then
  echo ">>> installing ossmate CLI (editable)"
  # --no-deps skips the PyPI resolve for ossmate-mcp; the editable install
  # above already satisfies that requirement from source.
  python -m pip install -e "./cli/ossmate[dev]" --no-deps
fi

echo ">>> verifying version sync"
python scripts/bump_version.py --check

echo ">>> done. Try:  ossmate --help   |   python -m ossmate_mcp --help"
