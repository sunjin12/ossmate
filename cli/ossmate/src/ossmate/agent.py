"""Thin wrapper around `claude-agent-sdk` that runs a Skill against the live
Claude API, registering Ossmate's MCP server as a stdio subprocess.

The SDK is imported lazily so that:
  - `ossmate --help` and `ossmate <cmd> --dry-run` work without the SDK installed
    (useful for CI matrix runs that only contract-test argument parsing).
  - Tests stay hermetic — the CLI tests never need to monkeypatch network calls.
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from .prompts import Skill, render
from .tools.repo import mcp_server_config


@dataclass
class RunRequest:
    skill: Skill
    args: list[str]
    project_root: Path
    dry_run: bool = False
    model_override: str | None = None


def _build_options(req: RunRequest) -> dict[str, object]:
    """Compose the ClaudeAgentOptions dict.

    Returned as a plain dict so the dry-run path can serialize it without
    touching the SDK. The actual SDK call constructs the dataclass inside
    `_run_live`.
    """
    return {
        "model": req.model_override or req.skill.model,
        "cwd": str(req.project_root),
        "system_prompt": (
            "You are Ossmate's CLI runner. The user invoked you outside Claude Code, "
            "so you do not have slash commands or interactive prompts available. "
            "Execute the skill body below as if it were the user's only message; "
            "follow its workflow exactly. Never assume confirmation — when the skill "
            "says `wait for user approval`, end your turn and print the proposed action."
        ),
        "mcp_servers": {
            "ossmate": mcp_server_config(req.project_root),
        },
        "allowed_tools": req.skill.allowed_tools,
    }


async def _run_live(req: RunRequest, prompt: str) -> int:
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
    except ImportError as exc:
        sys.stderr.write(
            "claude-agent-sdk is not installed. "
            "Run `pipx install ossmate` or `pip install claude-agent-sdk` first.\n"
            f"(import error: {exc})\n"
        )
        return 2

    raw = _build_options(req)
    options = ClaudeAgentOptions(
        model=raw["model"],
        cwd=raw["cwd"],
        system_prompt=raw["system_prompt"],
        mcp_servers=raw["mcp_servers"],
        allowed_tools=raw["allowed_tools"] or None,
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        async for message in client.receive_response():
            sys.stdout.write(str(message))
            sys.stdout.write("\n")
    return 0


def run(req: RunRequest) -> int:
    """Synchronous entry point used by the Typer subcommands."""
    prompt = render(req.skill, req.args)

    if req.dry_run:
        payload = {
            "skill": req.skill.name,
            "skill_source": str(req.skill.source_path),
            "args": req.args,
            "project_root": str(req.project_root),
            "options": _build_options(req),
            "rendered_prompt_preview": prompt[:500] + ("…" if len(prompt) > 500 else ""),
            "rendered_prompt_chars": len(prompt),
        }
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False))
        sys.stdout.write("\n")
        return 0

    return asyncio.run(_run_live(req, prompt))
