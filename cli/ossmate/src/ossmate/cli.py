"""Ossmate CLI — Typer subcommands that mirror the slash commands in
`.claude/commands/`. Each subcommand loads its skill .md file, renders any
`$1` / `$ARGUMENTS` placeholders, and either prints a dry-run plan or hands
the prompt to `claude-agent-sdk`.

The subcommand name MATCHES the skill filename. This is the single
mapping rule — `ossmate stale-sweep --days 60` runs `.claude/commands/stale-sweep.md`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from . import __version__
from .agent import RunRequest, run
from .prompts import SkillNotFoundError, load_skill
from .tools.repo import ProjectRootNotFoundError, find_project_root

app = typer.Typer(
    name="ossmate",
    help="OSS Maintainer's co-pilot — runs the same workflows as the Claude Code "
    "plugin, but from your terminal or CI.",
    no_args_is_help=True,
    add_completion=False,
)


def _common_dry_run() -> typer.Option:
    return typer.Option(
        False,
        "--dry-run",
        help="Print the rendered prompt + ClaudeAgentOptions without contacting the API.",
    )


def _common_cwd() -> typer.Option:
    return typer.Option(
        None,
        "--cwd",
        help="Override the project root (defaults to walking up from the current dir).",
    )


def _common_model() -> typer.Option:
    return typer.Option(
        None,
        "--model",
        help="Override the skill's default model (e.g., `claude-haiku-4-5-20251001`).",
    )


def _resolve_root(cwd: Path | None) -> Path:
    try:
        return find_project_root(cwd)
    except ProjectRootNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc


def _dispatch(skill_name: str, args: list[str], *, dry_run: bool, cwd: Path | None,
              model: str | None) -> None:
    project_root = _resolve_root(cwd)
    try:
        skill = load_skill(skill_name, project_root)
    except SkillNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc

    code = run(
        RunRequest(
            skill=skill,
            args=args,
            project_root=project_root,
            dry_run=dry_run,
            model_override=model,
        )
    )
    if code != 0:
        raise typer.Exit(code)


# ---- subcommands (one per skill) ----------------------------------------


@app.command("triage-pr", help="Triage a GitHub PR — read diff, classify, draft a review reply.")
def triage_pr(
    pr: str = typer.Argument(..., help="PR number or full GitHub URL."),
    dry_run: bool = _common_dry_run(),
    cwd: Path | None = _common_cwd(),
    model: str | None = _common_model(),
) -> None:
    _dispatch("triage-pr", [pr], dry_run=dry_run, cwd=cwd, model=model)


@app.command("triage-issue", help="Triage a GitHub issue — classify, suggest labels, draft reply.")
def triage_issue(
    issue: str = typer.Argument(..., help="Issue number or URL."),
    dry_run: bool = _common_dry_run(),
    cwd: Path | None = _common_cwd(),
    model: str | None = _common_model(),
) -> None:
    _dispatch("triage-issue", [issue], dry_run=dry_run, cwd=cwd, model=model)


@app.command("release-notes", help="Draft Keep-a-Changelog release notes for a version tag.")
def release_notes(
    version: str = typer.Argument(..., help="Version, e.g. v1.4.0 or 1.4.0."),
    since: str | None = typer.Option(None, "--since", help="Ref or ISO date to diff from."),
    dry_run: bool = _common_dry_run(),
    cwd: Path | None = _common_cwd(),
    model: str | None = _common_model(),
) -> None:
    args = [version]
    if since:
        args += ["--since", since]
    _dispatch("release-notes", args, dry_run=dry_run, cwd=cwd, model=model)


@app.command(
    "stale-sweep",
    help="Find issues older than N days and propose nudge / close / wontfix.",
)
def stale_sweep(
    days: int = typer.Option(60, "--days", help="Inactivity threshold in days."),
    label: str | None = typer.Option(None, "--label", help="Restrict to a single label."),
    dry_run: bool = _common_dry_run(),
    cwd: Path | None = _common_cwd(),
    model: str | None = _common_model(),
) -> None:
    args = ["--days", str(days)]
    if label:
        args += ["--label", label]
    _dispatch("stale-sweep", args, dry_run=dry_run, cwd=cwd, model=model)


@app.command(
    "onboard-contributor",
    help="Draft a warm welcome comment for a first-time contributor.",
)
def onboard_contributor(
    number: str = typer.Argument(..., help="PR or issue number."),
    dry_run: bool = _common_dry_run(),
    cwd: Path | None = _common_cwd(),
    model: str | None = _common_model(),
) -> None:
    _dispatch("onboard-contributor", [number], dry_run=dry_run, cwd=cwd, model=model)


@app.command("audit-deps", help="Audit lockfiles for OSV.dev advisories and stale direct deps.")
def audit_deps(
    ecosystem: str | None = typer.Option(
        None, "--ecosystem", help="One of: npm, pypi, crates.io. Defaults to all detected."
    ),
    dry_run: bool = _common_dry_run(),
    cwd: Path | None = _common_cwd(),
    model: str | None = _common_model(),
) -> None:
    args: list[str] = []
    if ecosystem:
        args += ["--ecosystem", ecosystem]
    _dispatch("audit-deps", args, dry_run=dry_run, cwd=cwd, model=model)


@app.command(
    "security-review-pr",
    help="Deep security review of a PR — secrets, injection, auth, supply chain, CI workflows.",
)
def security_review_pr(
    pr: str = typer.Argument(..., help="PR number."),
    focus: str | None = typer.Option(
        None, "--focus", help="Comma-separated focus areas (e.g., auth,ci,supply-chain)."
    ),
    dry_run: bool = _common_dry_run(),
    cwd: Path | None = _common_cwd(),
    model: str | None = _common_model(),
) -> None:
    args = [pr]
    if focus:
        args += ["--focus", focus]
    _dispatch("security-review-pr", args, dry_run=dry_run, cwd=cwd, model=model)


@app.command(
    "changelog-bump",
    help="Inspect Conventional Commits and propose the next semver bump.",
)
def changelog_bump(
    since: str | None = typer.Option(None, "--since", help="Ref or ISO date to diff from."),
    dry_run: bool = _common_dry_run(),
    cwd: Path | None = _common_cwd(),
    model: str | None = _common_model(),
) -> None:
    args: list[str] = []
    if since:
        args += ["--since", since]
    _dispatch("changelog-bump", args, dry_run=dry_run, cwd=cwd, model=model)


@app.command("version", help="Print the CLI version and exit.")
def version_cmd() -> None:
    sys.stdout.write(f"ossmate {__version__}\n")


@app.command("doctor", help="Run diagnostic checks for the Ossmate environment.")
def doctor(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of pretty output.",
    ),
    cwd: Path | None = _common_cwd(),
) -> None:
    from .diagnostics import render_json, render_pretty, run_all

    results = run_all(cwd)
    if json_output:
        sys.stdout.write(render_json(results) + "\n")
    else:
        render_pretty(results)
    if any(r.status == "fail" for r in results):
        raise typer.Exit(1)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    app()
