---
name: mr-human-review-dashboard
description: Generate a single self-contained HTML dashboard that explains a merge request or pull request for human reviewers. Use when an agent is asked to make an MR or PR diff readable, explain architecture impact, build a reviewer reading order, map review risk, write the report outside the workdir under ~/.ai-reviews/mr-human-review-dashboard, and open it in the user's default browser.
---

# MR Human Review Dashboard

## Purpose

Create one self-contained HTML file that makes the current merge request or pull request understandable for a human reviewer.

Do not explain files alphabetically or by raw diff order. Build a human reading path: intent, architecture surfaces, first files to inspect, mechanical fallout, and review risks.

## Ground Rules

- Work from the current repository, but do not write the report into the repository.
- Do not modify product code, tests, schemas, generated app assets, project configuration, or repository files.
- The only intended write is the generated HTML file reserved by the bundled helper script in `prepare` mode.
- Write reports under `~/.ai-reviews/mr-human-review-dashboard/<repo-slug>/`.
- Generate a new report for every run. Never overwrite an existing report.
- Separate repository facts from agent interpretation.
- Do not invent motivation. When intent is not explicit in commits, docs, branch names, or code, label it as `inferred`.
- Prefer concrete file paths, functions, classes, types, commands, and contracts over general commentary.
- Avoid full diff dumps. Include only short, relevant hunks or code excerpts.
- Keep local repository paths as plain text in the HTML. Do not create `file://` links or relative links to workdir files.

## Required Workflow

1. Read local agent and project guidance when present: `AGENTS.md`, `CLAUDE.md`, `README`, `CONTRIBUTING`, architecture docs, design docs, and relevant testing docs.
2. Resolve the bundled helper script to an absolute path from this installed skill folder. Keep the current working directory in the repository being reviewed. Do not `cd` into the skill folder to run the helper.

```bash
HELPER="/absolute/path/to/mr-human-review-dashboard/scripts/prepare-review-output.sh"
```

3. Run the helper before inspecting the diff in depth:

```bash
"$HELPER" prepare
```

If the harness or model is certainly known from the current runtime, pass it explicitly:

```bash
"$HELPER" prepare --harness "Codex" --model "GPT-5"
```

Do not guess harness or model. If they are not certainly known, omit the arguments; the script will emit `unknown`.

4. Parse the `KEY='VALUE'` lines as text. Do not `eval` or source this output. Use the emitted values for all later steps, especially:

- `BASE_REF`
- `BASE_SHA`
- `CURRENT_BRANCH`
- `HEAD_SHA`
- `REPO_ROOT`
- `REPO_SLUG`
- `REVIEW_TITLE`
- `REVIEW_KIND`
- `REVIEW_NUMBER`
- `REVIEW_URL`
- `PLATFORM`
- `OUTPUT_PATH`
- `OUTPUT_DIR`
- `CREATED_AT`
- `HARNESS`
- `MODEL`

5. If `prepare` reports multiple PR/MR candidates, ask the user which review to use, then rerun with the selected number or URL:

```bash
"$HELPER" prepare --review 123
```

6. Use the emitted `BASE_REF` for every diff command. Do not recompute or substitute the base branch later.

7. Inspect the diff with:

```bash
git diff --stat "$BASE_REF"...HEAD
git diff --name-status "$BASE_REF"...HEAD
git diff --find-renames "$BASE_REF"...HEAD
git diff "$BASE_REF"...HEAD
```

The prepare script aborts if the current directory is not inside a Git repository, no base can be resolved, or the diff is empty.

8. Read relevant architecture, design, and testing documentation selectively. Do not load unrelated documentation.
9. Read the most important changed code files and tests in full enough to understand behavior. Do not rely only on the diff.
10. Distinguish real behavior changes from mechanical, generated, formatting, dependency, or rename-only changes.
11. Write the final self-contained HTML to exactly `OUTPUT_PATH`. The path has already been atomically reserved; overwrite only that reserved file with the finished report.
12. After writing a non-empty HTML file, open it best-effort:

```bash
"$HELPER" open "$OUTPUT_PATH"
```

Browser opening is best-effort. If opening fails, still finish successfully and provide the report path.

13. Final chat response must be a short English sentence with the absolute path:

```text
Review: /absolute/path/to/report.html
```

## Output Naming

Reports are written to:

```text
~/.ai-reviews/mr-human-review-dashboard/<repo-slug>/<review-slug>-<timestamp>.html
```

The helper script derives:

- `<repo-slug>` from `owner/repo` remote path when available, otherwise the local repository directory name.
- `<review-slug>` from PR/MR title, otherwise branch name, otherwise short commit subject, otherwise `review`.
- `pr-<number>-...` for GitHub pull requests when the number is known.
- `mr-<number>-...` for GitLab merge requests when the number is known.
- Timestamp from local time in `YYYY-MM-DD-HHMMSS` format.

Slug rules:

- Lowercase.
- ASCII transliteration where available.
- Replace non-alphanumeric runs with `-`.
- Trim leading and trailing `-`.
- Limit review slug to 80 characters.
- Limit repository slug to 120 characters.

If a filename collides, the helper script appends `-2`, `-3`, and so on. It reserves the final path with an empty file before returning it.

## Required HTML Properties

The file must be:

- A single self-contained HTML document with embedded CSS and minimal JavaScript.
- Directly readable in a browser with no build step.
- Fully offline: no external assets, fonts, scripts, stylesheets, CDN resources, or network dependencies.
- Responsive and usable on desktop and mobile.
- A quiet review dashboard, not a marketing page.
- Structured with semantic sections, cards, badges, and collapsible details.

Do not use external assets, external scripts, external stylesheets, relative links to workdir files, `file://` links, or large complete diffs.

## Metadata

Show these values visibly in the header when available:

- Local repository path.
- Absolute output path.
- Platform.
- Review kind and number.
- Base ref and short base SHA.
- Current branch and short head SHA.
- Harness.
- Model.

If harness or model is `unknown`, explain in the HTML that `unknown` means `not available to the agent runtime`.

Also include a machine-readable metadata block:

```html
<script type="application/json" id="review-metadata">
{
  "generator": "mr-human-review-dashboard",
  "harness": "unknown",
  "model": "unknown",
  "unknownMeaning": "not available to the agent runtime",
  "repoRoot": "...",
  "repoSlug": "...",
  "baseRef": "...",
  "baseSha": "...",
  "currentBranch": "...",
  "headSha": "...",
  "platform": "...",
  "reviewKind": "...",
  "reviewNumber": "...",
  "reviewTitle": "...",
  "reviewUrl": "...",
  "outputPath": "...",
  "createdAt": "YYYY-MM-DD-HHMMSS"
}
</script>
```

Use full SHAs in JSON and shortened SHAs in visible UI.

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

- MR or PR title, derived from PR/MR metadata, branch, or commits if no explicit title is available.
- Base branch and short base SHA.
- Current branch and short head SHA.
- Platform and PR/MR number when known.
- Local repository path.
- Absolute output path.
- Harness and model.
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
