# Notes for `mr-human-review-dashboard`

Status: early feedback notes, not implementation requirements.

## Overall assessment

The core idea is strong: the skill does not try to replace human review. It tries to make review easier to digest when coding agents increase code volume. That is the right problem framing.

The strongest parts of the current skill are:

- External output under `~/.ai-reviews/mr-human-review-dashboard/...`, keeping reviewed repositories clean.
- A human reading order instead of alphabetic or raw diff order.
- Explicit separation between repository facts and agent interpretation.
- The `Show agent annotations` toggle, because it makes trust boundaries visible.
- A helper script that reserves output paths, resolves review metadata, and keeps naming deterministic.
- Review structure that forces the agent to consider architecture, risk, tests, and concrete files together.

## Main concern: scope and cognitive load

The required dashboard structure is good for large or high-risk MRs, but may be too heavy for small changes.

Current required sections include:

- Header
- TL;DR
- Human Reading Order
- Architecture Context
- Change Story
- Risk Map
- File Tour
- Design / Architecture Notes
- Test & Verification Plan
- Reviewer Checklist

For small MRs this could recreate the exact problem the skill is trying to solve: too much surface area for the reviewer.

### Suggested change: review modes

Add explicit output modes:

#### `quick`

Use for small MRs, mechanical changes, or reviewer triage.

Possible structure:

- Header / metadata
- 3-sentence TL;DR
- Changed files grouped by risk
- Top 3 review questions
- Minimal test / verification commands

No diagram required unless architecture changed.

#### `standard`

Current default target.

Possible structure:

- Header
- TL;DR
- Reading Order
- Risk Map
- File Tour for meaningful changes
- Test & Verification Plan
- Checklist

Diagram optional unless it clarifies the change.

#### `deep`

Use for large, architectural, persistence, security, concurrency, runtime, migration, or cross-boundary MRs.

Possible structure:

- Full current structure
- Required architecture diagram
- More detailed Design / Architecture Notes
- More explicit rollback / migration / runtime concerns

## Suggested change: review budget

Add a budget rule so the output remains digestible:

- Explain at most 5 high-attention files in detail by default.
- Group mechanical or safe files instead of creating full cards for each one.
- Prefer file groups over individual cards when changes are repetitive.
- If more than 5 files are high-risk, say that explicitly and show why.

This would help prevent dashboards from turning into another giant review artifact.

## Suggested change: anti-noise rules

Add stronger rules for what not to include:

- Do not create a verbose card for every formatting-only, rename-only, generated, or mechanical file.
- Do not repeat the same risk explanation across many files; group it once.
- Do not include a diagram if the diff is purely local and the diagram would be decorative.
- Do not turn every observation into a recommendation.

## Suggested addition: HTML template

A bundled template would be useful, especially if modes are added.

Possible location:

```text
skills/mr-human-review-dashboard/assets/dashboard-template.html
```

Template goals:

- Self-contained offline HTML.
- Embedded CSS and minimal JavaScript.
- Prebuilt layout for header, metadata, risk map, reading order, file cards, and checklist.
- Built-in `Show agent annotations` toggle.
- Clear CSS classes for facts vs. agent annotations.
- Responsive layout.

Useful placeholder style:

```html
<!-- {{HEADER}} -->
<!-- {{METADATA_JSON}} -->
<!-- {{TLDR}} -->
<!-- {{RISK_MAP}} -->
```

The skill can instruct agents to copy the template and replace placeholders, rather than inventing a new UI every run.

## Safety / correctness notes

### Escape embedded content

The skill should explicitly require HTML escaping for all code excerpts, diff hunks, file paths, branch names, commit messages, PR/MR titles, and metadata values inserted into HTML.

Without that, a diff or commit message could break the document or inject active markup/script.

Suggested rule:

> Escape all repository-derived text before inserting it into HTML. Use text nodes or equivalent escaping; never paste raw diff content as HTML.

### Browser opening is a visible side effect

Opening the generated report is useful, but it is a visible side effect. The skill already says best-effort; consider making it more explicit in the description or workflow:

> This skill writes an external HTML file and attempts to open it in the user's default browser.

### Empty reserved files

The helper reserves an empty output file before generation. If the agent crashes after `prepare`, an empty file can remain. That is acceptable, but worth documenting as expected behavior or optionally cleaning up if generation fails.

### GitLab JSON parsing fragility

The `glab` path parses JSON with `sed`, which is portable but fragile for more complex JSON shapes or escaped values. Fine for a first version; later, consider using `glab --jq`, `jq` when available, or a narrower documented compatibility expectation.

## Trigger / description notes

The current skill description is very long and includes detailed workflow behavior. That may be fine for early OpenAI skill triggering, but later it could be tightened.

Possible shorter direction:

> Generate an external self-contained HTML dashboard that makes a pull request or merge request easier for human reviewers to understand. Use when asked to explain a PR/MR diff, build a review reading order, triage risk, or make code review output more digestible. Writes under `~/.ai-reviews/mr-human-review-dashboard` and may open the report in the default browser.

Keep detailed workflow instructions in the body.

## Product framing

The best framing is not "AI code review". It is:

> Coding agents increase code volume; human review attention does not scale the same way. This skill turns diffs into a reading path, risk map, and verification plan so reviewers can spend attention where it matters.

That framing keeps the human reviewer central and avoids implying that the agent replaces review.
