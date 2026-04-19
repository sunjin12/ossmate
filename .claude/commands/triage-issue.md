---
description: Triage a GitHub issue — classify, suggest labels, draft a maintainer response
argument-hint: <issue-number-or-url>
allowed-tools: Bash(gh issue view:*) Bash(gh issue list:*) Bash(gh label list:*) Bash(gh repo view:*) Read Grep Glob
model: claude-sonnet-4-6
---

# /triage-issue

You are triaging issue **$1** as the OSS maintainer of this repository.

> If `$1` is empty, stop and ask the user for an issue number or URL. Do NOT guess.
> If `$1` looks like a URL (`https://github.com/owner/repo/issues/N`), extract `N`.

## Workflow

### Step 1 — Gather

Run these in parallel (one Bash call per command, all in the same response):

- `!gh issue view $1 --json number,title,body,labels,author,createdAt,updatedAt,state,comments,assignees,milestone`
- `!gh label list --limit 200 --json name,description,color` (so you propose only labels that actually exist)
- `!gh repo view --json name,nameWithOwner,description` (for context in your response)

If `gh issue view` fails (404, auth error, no `gh` installed), report the exact error and stop. Do not invent issue contents.

### Step 2 — Classify

Read [CONTRIBUTING.md](CONTRIBUTING.md) and [README.md](README.md) for project conventions, then classify into one of:

- **bug** — a defect: incorrect behavior, crash, regression
- **feature** — a new capability the project does not yet have
- **enhancement** — improvement to an existing feature (faster, clearer, more flexible)
- **question** — user is asking how to use something; no code change implied
- **docs** — documentation gap or error
- **duplicate** — same as another open or closed issue (cite which one)
- **invalid** — not actionable: spam, off-topic, missing repro
- **needs-info** — actionable in principle but author must supply more (repro steps, version, logs)

Use `gh issue list --state all --search "<keywords from title>" --json number,title,state --limit 10` to detect duplicates before classifying. Cite the duplicate's number if found.

### Step 3 — Output (use the `maintainer` output style format)

Lead line: `Issue #$1 → <classification> [confidence: high|medium|low]`

Then this exact structure:

**Decisions needed**
- [ ] Apply label(s): `<label-1>`, `<label-2>` (only labels that exist in the repo)
- [ ] Set priority: `priority/{low,medium,high,critical}` (omit if you cannot infer)
- [ ] Assign to: <suggestion or `(none — needs maintainer pick)`>
- [ ] If `duplicate` or `invalid`: close with comment? (yes/no)

**Why this classification**
- 2-3 bullets citing specific quotes from the issue body or linked artifacts.

**Proposed reply**

```markdown
<!-- proposed comment for issue #$1 -->
Hi @<author>,

<warm, specific acknowledgment of the contribution — never dismissive>

<one of:>
  - For bug: ask for missing repro details OR confirm reproduction OR assign milestone
  - For feature: link to roadmap discussion OR ask scope-narrowing question OR accept with caveat
  - For question: answer or link to docs section
  - For duplicate: link the original issue and close politely
  - For needs-info: list exactly what you need, in a numbered list

<sign-off matching project tone>
```

### Step 4 — Wait for user approval

Do NOT post the comment, apply labels, or close the issue. The user reviews your output and runs the necessary `gh` commands themselves (or grants permission case by case).

## Constraints

- RISK: Never invoke `gh issue close`, `gh issue comment`, `gh issue edit`, `gh label add`, or `gh issue lock` from this skill. These mutate state.
- If the issue has > 20 comments, summarize the conversation arc before classifying — but still cite specific comments by their position (e.g., "comment 14 from @other-user clarifies …").
- If the issue is in a language other than English, classify in the issue's language and produce the proposed reply in the same language.
