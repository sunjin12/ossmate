#!/usr/bin/env bash
# Ossmate status line — runs after every assistant turn.
#
# Reads a JSON payload on stdin (cwd, model, workspace, session_id, ...) and
# prints up to two lines to stdout. ANSI colors are supported.
#
# Layout:
#   [model]  branch:NAME  PRs:N  stale:M  tag:vX.Y.Z
#   ctx N% | $X.XX
#
# Cross-platform note: this script also has a sibling .cmd version at
# .claude/statusline.cmd for environments without bash. settings.json points
# to whichever one is active.

set -euo pipefail

INPUT="$(cat)"

# --- helpers -----------------------------------------------------------------
# Prefer jq if available; otherwise fall back to python3 for JSON parsing.
jget() {
    local path="$1"
    if command -v jq >/dev/null 2>&1; then
        printf '%s' "$INPUT" | jq -r "$path // empty"
    else
        printf '%s' "$INPUT" | python -X utf8 -c "
import json, sys
data = json.load(sys.stdin)
keys = '''$path'''.lstrip('.').split('.')
for k in keys:
    if isinstance(data, dict):
        data = data.get(k, '')
    else:
        data = ''
        break
print(data if data is not None else '')
" 2>/dev/null || echo ""
    fi
}

# --- extract fields ----------------------------------------------------------
MODEL_NAME="$(jget '.model.display_name')"
PROJECT_DIR="$(jget '.workspace.project_dir')"
CTX_PCT="$(jget '.context_window.used_percentage')"
COST_USD="$(jget '.cost.total_cost_usd')"

[ -z "$PROJECT_DIR" ] && PROJECT_DIR="$(jget '.cwd')"

# --- git info (cheap; gracefully degrades) -----------------------------------
BRANCH=""
if [ -n "$PROJECT_DIR" ] && [ -d "$PROJECT_DIR/.git" ]; then
    BRANCH="$(git -C "$PROJECT_DIR" symbolic-ref --short HEAD 2>/dev/null || echo 'detached')"
fi

LAST_TAG=""
if [ -n "$PROJECT_DIR" ] && [ -d "$PROJECT_DIR/.git" ]; then
    LAST_TAG="$(git -C "$PROJECT_DIR" describe --tags --abbrev=0 2>/dev/null || echo '')"
fi

# --- gh info (only if gh installed and authenticated) ------------------------
PR_COUNT=""
STALE_COUNT=""
if command -v gh >/dev/null 2>&1 && [ -n "$PROJECT_DIR" ]; then
    PR_COUNT="$(cd "$PROJECT_DIR" && gh pr list --state open --json number 2>/dev/null | python -X utf8 -c 'import json,sys; print(len(json.load(sys.stdin)))' 2>/dev/null || echo '')"
    STALE_COUNT="$(cd "$PROJECT_DIR" && gh issue list --state open --search 'updated:<2026-02-19' --json number 2>/dev/null | python -X utf8 -c 'import json,sys; print(len(json.load(sys.stdin)))' 2>/dev/null || echo '')"
fi

# --- color codes -------------------------------------------------------------
PURPLE=$'\033[38;5;141m'
CYAN=$'\033[38;5;87m'
YELLOW=$'\033[38;5;221m'
GREEN=$'\033[38;5;120m'
GRAY=$'\033[38;5;245m'
RESET=$'\033[0m'

# --- compose line 1 ----------------------------------------------------------
LINE1="${PURPLE}[${MODEL_NAME:-claude}]${RESET}"
[ -n "$BRANCH" ]      && LINE1="$LINE1  ${CYAN}branch:${BRANCH}${RESET}"
[ -n "$PR_COUNT" ]    && [ "$PR_COUNT" != "0" ] && LINE1="$LINE1  ${YELLOW}PRs:${PR_COUNT}${RESET}"
[ -n "$STALE_COUNT" ] && [ "$STALE_COUNT" != "0" ] && LINE1="$LINE1  ${GRAY}stale:${STALE_COUNT}${RESET}"
[ -n "$LAST_TAG" ]    && LINE1="$LINE1  ${GREEN}tag:${LAST_TAG}${RESET}"

# --- compose line 2 ----------------------------------------------------------
LINE2=""
if [ -n "$CTX_PCT" ]; then
    LINE2="${GRAY}ctx ${CTX_PCT}%${RESET}"
fi
if [ -n "$COST_USD" ]; then
    [ -n "$LINE2" ] && LINE2="$LINE2 ${GRAY}|${RESET} "
    LINE2="${LINE2}${GRAY}\$${COST_USD}${RESET}"
fi

# --- output ------------------------------------------------------------------
printf "%b\n" "$LINE1"
[ -n "$LINE2" ] && printf "%b\n" "$LINE2"
