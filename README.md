# Skills

A public collection of tool-neutral agent skills.

## Included Skills

| Skill | Purpose |
| --- | --- |
| [`mr-human-review-dashboard`](skills/mr-human-review-dashboard/SKILL.md) | Generates a self-contained HTML dashboard that explains a merge request or pull request for human reviewers. |
| [`xquik-x-data`](skills/xquik-x-data/SKILL.md) | Guides Codex through Xquik MCP setup, REST API integration, monitors, webhooks, and public X data workflows. |

## Installation

Clone this repository and copy the skill folder into the skill directory used by your agent harness:

```bash
git clone https://github.com/mrsOwlex/Skills.git
cp -R Skills/skills/mr-human-review-dashboard /path/to/your/agent/skills/
```

Then invoke the skill explicitly:

```text
Use $mr-human-review-dashboard to create a self-contained HTML review dashboard for the current merge request.
```

## Output Location

The review dashboard is not written into the current repository. Each run creates a new report under:

```text
~/.ai-reviews/mr-human-review-dashboard/<repo-slug>/<review-name>-<timestamp>.html
```

When a PR or MR number is available, filenames include `pr-<number>-...` for GitHub or `mr-<number>-...` for GitLab. The skill opens the generated report in the user's default browser on a best-effort basis and still returns the absolute path.

## Repository Layout

```text
skills/
  mr-human-review-dashboard/
    SKILL.md
    agents/openai.yaml
    scripts/prepare-review-output.sh
  xquik-x-data/
    SKILL.md
    agents/openai.yaml
```

Each skill folder is kept focused on agent-facing instructions and optional bundled resources. Human-facing project documentation lives at the repository root.

## License

MIT License. See [`LICENSE`](LICENSE).
