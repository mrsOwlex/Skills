# Contributing

This repository stores Codex skills.

## Skill Guidelines

- Put each skill in `skills/<skill-name>/`.
- Use lowercase hyphen-case for skill names.
- Keep `SKILL.md` focused on instructions an agent needs to execute the task.
- Do not add per-skill README files unless there is a strong reason. Prefer root-level documentation for humans.
- Add `agents/openai.yaml` for UI metadata when useful.
- Keep bundled resources purposeful: `scripts/`, `references/`, or `assets/` only when they directly support the skill.

## Validation

Before publishing a skill, validate the folder with the Codex skill validator when available:

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/<skill-name>
```

For substantial skill changes, test the skill on a realistic task and inspect the generated artifact.
