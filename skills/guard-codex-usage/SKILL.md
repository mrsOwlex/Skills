---
name: guard-codex-usage
description: Protect shared Codex five-hour and weekly capacity with configurable absolute and pace gates, and arrange automatic continuation after a blocking reset. Use before expensive implementation, long build or test loops, subagent delegation, multi-agent orchestration, or whenever a project must preserve Codex capacity for a higher-priority workload; also use when installing or operating Codex usage hooks.
---

# Guard Codex Usage

Gate expensive Codex work with a deterministic, fail-closed check. Keep absolute limits separate from pace projections and make every threshold project-configurable.

## Check before expensive work

Run the global script from the current project:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/guard-codex-usage/scripts/check_usage.py" --json
```

The script discovers `.codex/usage-guard.json` from the working directory upward, then `~/.codex/usage-guard.json`. Use `--config PATH` to select one explicitly. Defaults preserve the proven policy: primary warn/block `80/90`, weekly warn/block `70/80`, primary pace ignored below `50`, weekly pace ignored below `70`, recheck every `900` seconds. Projects may set warning and hard limits to the same value when work should continue without a capacity-only warning until the hard stop.

## Obey the decision

- `allow`: continue the scoped work.
- `warn`: finish only the current bounded phase; do not start speculative work or new delegation; recheck before another expensive phase.
- `block`: start no new expensive GPT-backed work; stop owned long-running work when safe and leave resumable state. When the Codex automation tool is available, delete any older active guard-resume heartbeat for the current task and create a new one for a valid future `blockedUntil`; do not update an existing schedule because it may retain its original recurrence anchor. Calculate the seconds until the offset-bearing `blockedUntil`, round up to whole minutes, and create `FREQ=MINUTELY;INTERVAL=<minutes>;COUNT=2`. Creation is the first occurrence, so `COUNT=2` leaves exactly one future wakeup. Do not use a daily or wall-clock rule or Custom Time. Inspect the saved heartbeat and verify `FREQ=MINUTELY`, the calculated interval, and `COUNT=2`. The wakeup prompt must rerun this guard and automatically continue the interrupted task when no longer blocked; if still blocked, replace the expired heartbeat using the newly reported reset. Do not busy-wait.
- command, config, cache, or malformed-data error: fail closed for new expensive work and report the error. If the only scheduling blocker is an expired `blockedUntil`, do not create a zero or negative interval; create a one-minute relative retry heartbeat with `COUNT=2` when wakeups are available, then rerun the guard.

Follow configured `warnInstruction` or `blockInstruction` values when present. Use them for project-specific coordination such as notifying a designated operator and waiting for the reported reset; never hard-code a stakeholder into the global policy.

Never consume reset credits automatically. A pace warning never hard-blocks by itself. Configure `paceMinimumPercent` independently from the absolute warning threshold. Missing pace projections are acceptable and reported through `paceUnavailable`; malformed projections fail closed. If the primary usage window is absent or `null` while the weekly window is valid, evaluate the weekly window and report `primary` through `unavailableWindows`; a malformed present window remains a data error.

Recheck after the configured interval and before each new expensive phase. A cached block remains blocking only until the earlier of the configured interval and `blockedUntil`; at the reset boundary the hook must fetch fresh usage. Blocking prompt/session hooks leave the agent turn available for resumable-state and wakeup coordination, while pre-tool hooks continue denying expensive tools and explicitly allow only the automation-update tool needed for that coordination. If task wakeups are unavailable, report `blockedUntil` and the resumable state.

## Configure a project

Read [references/configuration.md](references/configuration.md) when creating project configuration or installing hooks. Keep hook installation project-local: a global skill supplies the mechanism, while each project chooses whether it should be gated.

## Verify the skill

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/guard-codex-usage/scripts/test_usage_guard.py"
uv run --with pyyaml python \
  "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" \
  "${CODEX_HOME:-$HOME/.codex}/skills/guard-codex-usage"
```
