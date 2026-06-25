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
- Embed every changed file's full diff exactly once, but keep it out of the calm surface: each diff lives inside a collapsible `<details>` — either attached to its reading-order step, or grouped in the collapsed "Agent-verified" section. Generate each diff block with the bundled helper (see below) and embed its output verbatim. Never hand-transcribe, summarize, abbreviate, stub, or replace diff lines with `…`/comment placeholders — this applies to ALL files including tests, generated files, and `.csproj` version bumps. All `<details>` holding a diff are collapsed by default to keep the surface calm; signal priority with the risk badge, not by auto-expanding.
- Link source files to their blob at the head commit using `REPO_WEB_URL` and `HEAD_SHA` (see "Source Links"). Keep local repository paths as plain text. Do not create `file://` links or relative links to workdir files.

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
- `REPO_WEB_URL`
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
11. Build the report from the bundled template. Read `assets/template.html` from this installed skill folder and use it as the scaffold:

```bash
TEMPLATE="/absolute/path/to/mr-human-review-dashboard/assets/template.html"
RENDER_DIFF="/absolute/path/to/mr-human-review-dashboard/scripts/render-diff.sh"
```

For each changed file, produce its diff block by running `"$RENDER_DIFF" "$BASE_REF" "<path>"` and pasting the emitted `<pre class="diff">…</pre>` verbatim into that file's `<details>`. This guarantees the complete, correctly escaped diff — do not edit or shorten it.

- Keep the `<style>` and both `<script>` blocks verbatim. They carry the high-contrast theme, the localStorage persistence for the annotation toggle / reviewer checklist / collapsible state, and the offline per-line syntax highlighter that colors the diff tokens. Do not reimplement persistence or highlighting by hand. The highlighter reads the `data-lang` attribute that `render-diff.sh` emits on each `<pre class="diff">` — so paste the helper's output verbatim (do not strip `data-lang`).
- Replace every `{{PLACEHOLDER}}` with real values from `prepare` output and the diff.
- Replicate the marked example blocks (reading-order steps, file rows, diff `<details>`, design-note groups, checklist items, mechanical files) once per real item, then delete any leftover example/placeholder markup.
- Replace every placeholder with a value from `prepare` output, the diff, or platform metadata. A few header bits are optional (`{{AUTHOR}}`, `{{STATE}}`, `{{TICKET_OR_EPIC}}`): when the platform CLI does not provide them, delete that element rather than leave a placeholder. Derive from `REVIEW_KIND` (`merge_request` | `pull_request`): `{{REVIEW_KIND_TITLE}}` (`Merge Request` | `Pull Request`), `{{REVIEW_KIND_SHORT}}` (`MR` | `PR`), and `{{REVIEW_NUMBER_PREFIX}}` (`!` for GitLab, `#` for GitHub). `{{FILE_URL}}` is computed per "Source Links".

No-review fallback: `prepare` can succeed with empty `REVIEW_KIND`, `REVIEW_NUMBER`, and `REVIEW_URL` (no PR/MR found — e.g. reviewing a local branch before opening one). In that case use a neutral kicker (`Branch Review · Human Review Dashboard`), delete the MR/PR link, number, and `Platform / kind` value from the header, and orient the reader with the branch name and head SHA instead. Source links still work from `REPO_WEB_URL` + `HEAD_SHA`.
- Write the finished, fully self-contained HTML to exactly `OUTPUT_PATH`. The path has already been atomically reserved; overwrite only that reserved file. The result must contain no `{{...}}` markers and no `<!-- EXAMPLE -->` / `<!-- REPEAT -->` / scaffold comments.
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

Do not use external assets, external scripts, external stylesheets, relative links to workdir files, or `file://` links. Full per-file diffs are allowed and expected, but only inside collapsible `<details>` so the default surface stays calm.

Readability and contrast are part of the bar: the bundled theme targets WCAG AA on the dark background. Do not lower text contrast, do not introduce faint gray body copy, and keep body text at the template's size or larger. Diff lines must stay legible (added/removed tinted, context still readable).

## Metadata

The header stays slim. Show only review-relevant facts at the top:

- MR or PR title.
- Ticket or epic tag and the MR/PR link.
- One short answer to: what is this about?
- Number of changed files, insertions, deletions, and at most a few review-relevant counts (e.g. new core files, DB migrations).

Move run/provenance metadata into a collapsed `Run details` disclosure (already in the template): harness, model, base ref and short base SHA, current branch and short head SHA, platform, local repository path, absolute output path. Reviewers should not have to look at agent/harness, commit SHAs, or repo paths to start reviewing.

If harness or model is `unknown`, explain in the HTML that `unknown` means `not available to the agent runtime`.

The machine-readable metadata block lives in the template (`<script id="review-metadata">`); fill its placeholders, including `repoWebUrl`. Use full SHAs in JSON and shortened SHAs in visible UI.

**Escape every substituted value**, not just diffs. Prepare-sourced text (especially `reviewTitle`) can contain characters that break the page:

- Inside the `review-metadata` JSON, JSON-escape values: escape `\` and `"`, and escape every `<` as the six-character JSON unicode escape (backslash, lowercase u, 0, 0, 3, c) so a title containing `</script>` cannot close the script tag.
- In visible HTML, HTML-escape `&`, `<`, `>` in text and also `"` inside attribute values.

A malformed title must never break the metadata block or break out of the script tag.

## Source Links

Make changed-file references clickable. Build a file-level blob link to the head commit from `REPO_WEB_URL` and `HEAD_SHA`:

- GitLab: `REPO_WEB_URL/-/blob/HEAD_SHA/PATH`
- GitHub: `REPO_WEB_URL/blob/HEAD_SHA/PATH`

Use the full `HEAD_SHA` so links stay stable. File-level links (no line anchor) are the default; only add a `#L<n>` anchor when you are confident of the line.

Per status:

- `NEW`, `MOD`, `RENAMED`: link the (new) path at `HEAD_SHA`.
- `DEL`: the file is gone at the head commit, so a `HEAD_SHA` link 404s. Link the old path at `BASE_SHA` instead (`.../blob/BASE_SHA/OLD_PATH`), or render it as plain text.

If `REPO_WEB_URL` is empty, or `PLATFORM` is neither `gitlab` nor `github` (so the blob path is unknown), render every path as plain text instead of a broken link.

## Agent Annotation Toggle

The template provides a visible toggle near the top labeled `Show agent annotations`, plus the persistence wiring. Your job is to mark content, not to rebuild the toggle.

- Mark all interpretive review comments, risks, recommendations, and review questions with the CSS class `.agent-annotation`.
- Facts from git, code, tests, and documentation must remain visible even when annotations are hidden.
- The toggle hides/shows `.agent-annotation` and persists in `localStorage`. The reviewer checklist and collapsible `<details data-key>` states also persist — this is handled by the template's `<script>` block, which you keep verbatim.

## Content Structure

The **Human Reading Order is the spine** of the dashboard. Do not build separate, parallel sections for risk, file tour, change story, and test plan that repeat the same files in a different order. Fold them into the reading order (risk as inline badges, per-file diffs as expandable detail) so a human walks one path. Tests and mechanical fallout move out of the spine entirely.

The section order is fixed by the template:

### 1. Header (slim)

See "Metadata". Visible: title, ticket/epic tag, MR/PR link, what-it's-about, change counts. Everything else (harness, model, SHAs, paths) goes in the collapsed `Run details` disclosure.

### 2. TL;DR

2 to 4 sentences:

- What changes functionally?
- What architecture decision or direction is visible?
- What must a reviewer understand before reviewing details?

### 3. Architecture Context

Explain the change in the existing system context. Derive relevant surfaces from repository documentation, module structure, and the diff (request/event flow, data flow, ownership boundaries, runtime processes, persistence, UI/API contracts, background jobs, external integrations).

Include one small diagram using the template's HTML/CSS flow blocks (or inline SVG) showing one of: before/after structure, changed runtime flow, or affected module boundaries. This section is high-value — keep it.

### 4. Human Reading Order (the spine)

A prioritized path based on how a human should understand the change, not on filenames. Aim for roughly 3 to 6 steps. Categories as appropriate: entry points, core domain flow, persistence/schema/migrations, API or UI boundary, integrations.

Do **not** add "Tests" or "Mechanical fallout" steps here — those belong in the collapsed "Agent-verified" section.

For every step include:

- A category label and, when it carries review risk, an inline risk badge (`attention`, `medium`, or `safe`) on the step. This replaces a standalone Risk Map — risk lives where the reading happens.
- Why to start/continue there and what it does.
- The files to read, each as a clickable source link (see "Source Links"), with a one-line note and a status badge (`new`, `mod`, `del`, `renamed`).
- One concrete thing the reviewer should check, marked `.agent-annotation`.
- A per-file `<details class="file">` carrying the **full diff** for each file in the step (this is the former "File Tour", now attached to the step it belongs to), produced by `render-diff.sh`. Keep all diff `<details>` collapsed by default to stay calm; the `attention`/`medium`/`safe` badge signals priority. Give each `<details>` a stable `data-key` so its state persists.

Keep the steps themselves prägnant — heavy content lives behind the collapsibles, not in the step summary.

### 5. Design / Architecture Notes

Group decisions by theme instead of a flat bullet dump (the template provides the groups):

- Coupling introduced or removed.
- Invariants that must still hold.
- Alternatives apparently not chosen (mark `inferred` when derived only from the diff).

Keep it tight and organized; avoid a long list of unrelated bullets.

### 6. Reviewer Checklist

A short checkbox list for the human reviewer. Each item gets a stable `data-check` id so progress survives reloads (template-handled). Tailor items to this MR (architecture understood, risky files reviewed, public contracts reviewed, runtime/migration/rollback questions resolved).

### 7. Agent-verified (collapsed)

A single collapsed `<details>` at the bottom for what an agent verifies more efficiently than a human: tests, mechanical/generated changes, version bumps, changelog edits. Each file here is a nested collapsed `<details>` with a linked path and its **complete** diff from `render-diff.sh` — the same standard as the spine. Do not reduce test files to method-name stubs and do not replace `.csproj`/`.props`/changelog diffs with synthetic one-line summaries. This keeps every diff present and complete without adding noise to the human path.

## Quality Bar

- Write for a reviewer who wants to understand the MR or PR quickly but correctly.
- Keep the dashboard calm, scannable, and low-noise. The spine should fit a quick scan; depth hides behind collapsibles.
- Make facts and interpretation visually distinguishable; keep interpretive content behind `.agent-annotation`.
- Prioritize readability and contrast (WCAG AA on the dark theme); never introduce faint, low-contrast text.
- Every changed file's diff is present exactly once, HTML-escaped, inside a collapsible.
- No leftover `{{placeholders}}` or example/REPEAT comments. The HTML works when opened directly in a browser, fully offline.
