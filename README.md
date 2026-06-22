# Skills

A public collection of Codex skills.

## Included Skills

| Skill | Purpose |
| --- | --- |
| [`mr-human-review-dashboard`](skills/mr-human-review-dashboard/SKILL.md) | Generates a self-contained `mr-human-review.html` dashboard that explains a merge request or pull request for human reviewers. |

## Installation

Clone this repository and copy the skill folder you want into your Codex skills directory:

```bash
git clone https://github.com/mrsOwlex/Skills.git
mkdir -p ~/.codex/skills
cp -R Skills/skills/mr-human-review-dashboard ~/.codex/skills/
```

Then invoke the skill explicitly:

```text
Use $mr-human-review-dashboard to create a self-contained HTML review dashboard for the current merge request.
```

## Repository Layout

```text
skills/
  mr-human-review-dashboard/
    SKILL.md
    agents/openai.yaml
```

Each skill folder is kept focused on Codex-facing instructions and optional bundled resources. Human-facing project documentation lives at the repository root.

## License

MIT License. See [`LICENSE`](LICENSE).
