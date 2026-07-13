# Skills

A public collection of tool-neutral agent skills.

## Included Skills

| Skill | Purpose |
| --- | --- |
| [`mr-human-review-dashboard`](skills/mr-human-review-dashboard/SKILL.md) | Generates a self-contained HTML dashboard that explains a merge request or pull request for human reviewers. |
| [`orchestrate-codex-tasks`](skills/orchestrate-codex-tasks/SKILL.md) | Delegates bounded work to visible Codex tasks, tracks durable workers, and consolidates verified results in the main task. |
| [`send-telegram-message`](skills/send-telegram-message/SKILL.md) | Sends an exact plaintext message through a Telegram bot configured with environment variables. |

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

For local development, a skill can instead be linked into Codex so repository changes are immediately available:

```bash
ln -s /absolute/path/to/Skills/skills/send-telegram-message ~/.codex/skills/send-telegram-message
```

The Telegram skill expects Node.js 18 or newer. It reads `TELEGRAM_BOT_TOKEN` and `OWNER_CHAT_ID` from the process environment or from the private user-level file `${XDG_CONFIG_HOME:-$HOME/.config}/codex/send-telegram-message.env`. The bundled configurator creates that file with mode `0600`; credentials are never stored in this repository, and the skill has no workspace-path or package dependency.

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
    assets/template.html
    scripts/prepare-review-output.sh
  orchestrate-codex-tasks/
    SKILL.md
    agents/openai.yaml
  send-telegram-message/
    SKILL.md
    agents/openai.yaml
    scripts/configure-telegram-env.mjs
    scripts/send-telegram-message.mjs
    scripts/telegram-config.mjs
    tests/mock-fetch.mjs
    tests/send-telegram-message.test.mjs
    tests/telegram-config.test.mjs
```

Each skill folder is kept focused on agent-facing instructions and optional bundled resources. Human-facing project documentation lives at the repository root.

## License

MIT License. See [`LICENSE`](LICENSE).
