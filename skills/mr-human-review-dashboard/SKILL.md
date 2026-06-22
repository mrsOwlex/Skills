---
name: mr-human-review-dashboard
description: Generate a single self-contained HTML dashboard that explains a merge request or pull request for human reviewers. Use when Codex is asked to make an MR or PR diff readable, explain architecture impact, build a reviewer reading order, map review risk, or create mr-human-review.html without changing product code.
---

# MR Human Review Dashboard

## Purpose

Create one self-contained `mr-human-review.html` file that makes the current merge request or pull request understandable for a human reviewer.

Do not explain files alphabetically or by raw diff order. Build a human reading path: intent, architecture surfaces, first files to inspect, mechanical fallout, and review risks.

## Ground Rules

- Work in the current repository.
- Do not modify product code, tests, schemas, generated app assets, or project configuration.
- The only intended write is `mr-human-review.html`.
- Separate repository facts from agent interpretation.
- Do not invent motivation. When intent is not explicit in commits, docs, branch names, or code, label it as `inferred`.
- Prefer concrete file paths, functions, classes, types, commands, and contracts over general commentary.
- Avoid full diff dumps. Include only short, relevant hunks or code excerpts.

## Context Gathering

1. Read local agent and project guidance when present: `AGENTS.md`, `CLAUDE.md`, `README`, `CONTRIBUTING`, architecture docs, design docs, and relevant testing docs.
2. Determine the base branch for the MR or PR. If the target is unclear, try `origin/main` first, then `main`.
3. Inspect the diff with:

```bash
git diff --stat <base>...HEAD
git diff --name-status <base>...HEAD
git diff --find-renames <base>...HEAD
git diff <base>...HEAD
```

4. Read relevant architecture, design, and testing documentation selectively. Do not load unrelated documentation.
5. Read the most important changed code files and tests in full enough to understand behavior. Do not rely only on the diff.
6. Distinguish real behavior changes from mechanical, generated, formatting, dependency, or rename-only changes.

## Required Output

Create `mr-human-review.html` in the current repository.

The file must be:

- A single self-contained HTML document with embedded CSS and minimal JavaScript.
- Directly readable in a browser with no build step.
- Responsive and usable on desktop and mobile.
- A quiet review dashboard, not a marketing page.
- Structured with semantic sections, cards, badges, and collapsible details.

Do not use external assets, external scripts, external stylesheets, or large complete diffs.

## Agent Annotation Toggle

Add a visible toggle near the top labeled `Show agent annotations`.

All interpretive review comments, risks, recommendations, and review questions from the agent must be marked with the CSS class `.agent-annotation`.

Facts from git, code, tests, and documentation must remain visible even when annotations are hidden.

The toggle must:

- Hide `.agent-annotation` elements when off.
- Show `.agent-annotation` elements when on.
- Persist its state with `localStorage`.

## Content Structure

### 1. Header

Include:

- MR or PR title, derived from branch or commits if no explicit title is available.
- Base branch.
- Current branch.
- Number of changed files.
- Added and deleted line counts.
- One short answer to: what is this MR or PR about?

### 2. TL;DR

Write 2 to 4 sentences:

- What changes functionally?
- What architecture decision or direction is visible?
- What must a reviewer understand before reviewing details?

### 3. Human Reading Order

Create a prioritized reading order based on how a human should understand the change, not on filenames.

Use categories as appropriate:

- Entry points
- Core domain flow
- Persistence, schema, or migrations
- API or UI boundary
- Integrations
- Tests
- Mechanical fallout

For every step, include:

- Why to start there.
- Which files to read.
- What the reviewer should check.

### 4. Architecture Context

Explain the change in the existing system context. Derive relevant architecture surfaces from repository documentation, module structure, and the diff.

Consider:

- Request or event flow
- Data flow
- Ownership boundaries
- Runtime processes
- Persistence
- UI or API contracts
- Background jobs
- External integrations

Include one small diagram using HTML/CSS or inline SVG. The diagram should show one of:

- Before and after structure.
- Changed runtime flow.
- Affected module boundaries.

### 5. Change Story

Explain the change as a sequence:

- What happened before?
- What happens after?
- Which new data, types, or contracts appear?
- Which old assumptions are removed?

### 6. Risk Map

Group changed files into three levels:

- `ATTENTION`: High review priority. Behavior, persistence, concurrency, security, runtime, migrations, or rollback risk.
- `MEDIUM`: Logic, API contracts, tests, or UI behavior.
- `SAFE`: Types, docs, mechanical renames, formatting, or pure callsite updates.

For every risky file, include:

- Risk in one sentence.
- Concrete review question.
- Relevant functions, classes, or types.

Mark risk explanations and review questions as `.agent-annotation`.

### 7. File Tour

Create collapsible cards for each changed file or file group.

Each card must include:

- Path.
- Status: `NEW`, `MOD`, `DEL`, or `RENAMED`.
- Risk badge.
- Why this change exists.
- What to check.
- At most 1 to 3 important code or diff excerpts.

High-risk cards should be open by default. Safe cards should be collapsed by default.

Mark interpretive guidance as `.agent-annotation`.

### 8. Design / Architecture Notes

List the most important design decisions:

- Which coupling is introduced or removed?
- Which ownership boundary shifts?
- Which invariants must still hold?
- Which alternatives does the MR or PR appear not to choose?

When something is derived only from the diff, write `inferred`.

### 9. Test & Verification Plan

Include:

- Existing tests that cover the change.
- Tests that may be missing.
- Useful manual checks.
- Concrete commands found in `package.json`, `Makefile`, `README`, CI configuration, or equivalent project files.

### 10. Reviewer Checklist

End with a short checkbox list:

- Architecture understood.
- Risky files reviewed.
- Public contracts reviewed.
- Tests reviewed.
- Runtime, migration, and rollback questions resolved.

## Quality Bar

- Write for a reviewer who wants to understand the MR or PR quickly but correctly.
- Keep the dashboard calm, dense, and scannable.
- Make facts and interpretation visually distinguishable.
- Keep code excerpts short and purposeful.
- Ensure the HTML works when opened directly in a browser.
