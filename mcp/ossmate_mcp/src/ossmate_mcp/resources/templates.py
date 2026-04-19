"""Template resources — reusable maintainer copy.

Skills and subagents reach for these via URIs like
``templates://release-notes`` so the wording lives in one place. Edit
the strings here when the project's voice or formatting changes.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

RELEASE_NOTES_TEMPLATE = """\
# {version} - {date}

> _One-paragraph summary of the release for humans, written in the
> maintainer voice (see `.claude/output-styles/maintainer.md`)._

## Highlights

- {highlight_1}
- {highlight_2}

## Added

- ...

## Changed

- ...

## Fixed

- ...

## Deprecated / Removed

- _(Omit this section if empty.)_

## Breaking

> Use the `**BREAKING:**` prefix on every bullet that requires user
> action. Mention the migration path inline.

- ...

## Contributors

Thanks to {contributors} for this release.
"""

ISSUE_STALE_NUDGE_TEMPLATE = """\
Hi {author}, this is a friendly nudge from the maintainer.

This issue has been open for {age_days} days without a reply on the
last update. We try to keep the queue tight so contributors know what's
actively being worked on.

A few options from here:

- If the issue is still relevant, leave any reply (even just \"yes\")
  and we'll pick it back up.
- If you've worked around it, a quick note about the workaround helps
  others searching the queue later.
- If you no longer need it, feel free to close — no offence taken.

If we don't hear back within {grace_days} days, we'll close this with
the `stale` label. It can be reopened any time.

Thanks for filing it in the first place.
"""

WELCOME_TEMPLATE = """\
Welcome, {author}, and thanks for opening your first PR against
{repo}!

A maintainer will look at this within {response_sla_days} days. In the
meantime, the items below help your change land smoothly:

- [ ] CI is green ({ci_link})
- [ ] The PR description explains the user-visible change
- [ ] If your change is user-facing, an entry has been added to
      `CHANGELOG.md` under `## [Unreleased]`
- [ ] You are happy for your contribution to be released under the
      project's license

If anything in our contribution guide is unclear, reply here and we'll
fix the docs. Glad to have you.
"""


def register(mcp: FastMCP) -> None:
    @mcp.resource("templates://release-notes")
    def release_notes() -> str:
        """Keep-a-Changelog-shaped release-notes skeleton with placeholders."""
        return RELEASE_NOTES_TEMPLATE

    @mcp.resource("templates://issue-stale-nudge")
    def stale_nudge() -> str:
        """Polite reminder posted on stale issues before the auto-close grace."""
        return ISSUE_STALE_NUDGE_TEMPLATE

    @mcp.resource("templates://welcome")
    def welcome() -> str:
        """First-time contributor welcome message + checklist."""
        return WELCOME_TEMPLATE
