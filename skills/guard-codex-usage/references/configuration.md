# Configuration and hooks

## Project configuration

Place `.codex/usage-guard.json` in a project or parent workspace:

```json
{
  "projectLabel": "Current project",
  "reserveLabel": "Reserved workload",
  "warnInstruction": "Notify the designated operator, finish the current bounded phase, then recheck.",
  "blockInstruction": "Record resumable state and wait until blockedUntil.",
  "recheckSeconds": 900,
  "windows": {
    "primary": {
      "paceMinimumPercent": 50,
      "warningPercent": 80,
      "hardPercent": 90
    },
    "secondary": {
      "paceMinimumPercent": 70,
      "warningPercent": 70,
      "hardPercent": 80
    }
  }
}
```

All fields are optional. `warnInstruction` and `blockInstruction` are surfaced in script and hook results but are never executed as shell commands. Unknown fields fail closed to catch misspellings. Each window must satisfy:

```text
0 <= paceMinimumPercent <= 100
0 <= warningPercent <= hardPercent <= 100
```

Set `warningPercent` equal to `hardPercent` when a window should have no capacity-only warning before its hard stop. Configure the pace floor independently; pace warnings never hard-block by themselves.

Discovery order:

1. `--config PATH`
2. `CODEX_USAGE_GUARD_CONFIG`
3. nearest `.codex/usage-guard.json` from the working directory upward
4. `${CODEX_HOME:-$HOME/.codex}/usage-guard.json`
5. built-in defaults

Use `--input fixture.json` to test a policy without calling `codexbar`.

## Project hook installation

Hooks are opt-in per project. Reference the global adapter from `.codex/hooks.json`:

```json
{
  "hooks": {
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "python3 \"${CODEX_HOME:-$HOME/.codex}/skills/guard-codex-usage/scripts/usage_guard_hook.py\"",
        "timeout": 15
      }]
    }],
    "UserPromptSubmit": [{
      "hooks": [{
        "type": "command",
        "command": "python3 \"${CODEX_HOME:-$HOME/.codex}/skills/guard-codex-usage/scripts/usage_guard_hook.py\"",
        "timeout": 15
      }]
    }],
    "PreToolUse": [{
      "matcher": "^(Bash|apply_patch|mcp__.*)$",
      "hooks": [{
        "type": "command",
        "command": "python3 \"${CODEX_HOME:-$HOME/.codex}/skills/guard-codex-usage/scripts/usage_guard_hook.py\"",
        "timeout": 15
      }]
    }]
  }
}
```

The adapter discovers configuration using the hook input `cwd`, caches by session, and invalidates the cache whenever the effective configuration changes or a cached block reaches `blockedUntil`. It writes cache files atomically under `${CODEX_HOME:-$HOME/.codex}/state/usage-guard`.

On a block, `SessionStart` and `UserPromptSubmit` inject blocking context without cancelling the agent turn so the agent can preserve state and arrange continuation. `PreToolUse` still denies matched tools, except an exact `automation_update` tool name or a namespaced name ending in `__automation_update`; this narrow exception exists only so the agent can create, inspect, replace, or delete its guard-resume heartbeat. Keep the matcher aligned with the tool names available in the project's Codex surface.

Hooks complement manual checks. They do not necessarily intercept every tool or external orchestration path, so manually check before subagent fan-out and long GPT-backed phases.

If CodexBar omits the primary window or returns it as `null` while the weekly window is valid, the guard evaluates the weekly window and records `primary` in `unavailableWindows`. Missing pace projections are recorded in `paceUnavailable`. Present but malformed data fails closed.
