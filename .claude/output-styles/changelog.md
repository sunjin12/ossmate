---
name: changelog
description: Forces Keep-a-Changelog format — one section per version with Added/Changed/Deprecated/Removed/Fixed/Security.
keep-coding-instructions: true
---

When asked to produce or update a changelog, ALL output must conform to [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

## Hard rules

1. Every version section uses the heading: `## [X.Y.Z] - YYYY-MM-DD` (or `## [Unreleased]`).
2. Subsections appear in this exact order, omitted if empty: **Added**, **Changed**, **Deprecated**, **Removed**, **Fixed**, **Security**.
3. Each bullet is one user-visible change in past tense imperative ("Added X", "Fixed Y"), not commit messages and not implementation details. The reader is a downstream consumer, not a contributor.
4. Reference PR/issue numbers in parentheses at the end: `(#1234)`. Multiple = `(#1234, #1240)`.
5. Breaking changes get a leading `**BREAKING:**` and live under **Changed** or **Removed**.
6. Bottom of file holds GitHub compare links: `[Unreleased]: https://github.com/owner/repo/compare/vX.Y.Z...HEAD`.

## Semver inference

When proposing a version bump from a list of merged PRs:
- ANY breaking change → **major**
- ANY new public API/feature with no breaking → **minor**
- Only fixes, internal refactors, docs, test, chore → **patch**

State your inference and the evidence: "Proposing **minor** bump to v1.4.0 because PR #310 adds `--watch` flag (new public surface) and no PRs introduce breaking changes."

## Don't

- Don't write paragraphs. Bullets only inside version sections.
- Don't list dependency bumps individually unless they are user-visible (e.g., dropped Python 3.10 support → that goes under **Removed**).
- Don't invent PR numbers — if unknown, omit the parenthetical.
