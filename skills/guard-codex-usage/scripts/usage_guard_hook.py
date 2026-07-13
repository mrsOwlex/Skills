#!/usr/bin/env python3
"""Project-hook adapter for the global configurable Codex usage guard."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import check_usage


VALID_EVENTS = {"SessionStart", "UserPromptSubmit", "PreToolUse"}


def _default_state_dir() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    return codex_home / "state" / "usage-guard"


def _state_path(state_dir: Path, session_id: str) -> Path:
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return state_dir / f"{digest}.json"


def _config_fingerprint(config: dict[str, Any]) -> str:
    encoded = json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_cached(
    path: Path,
    now: float,
    interval: int,
    config_fingerprint: str,
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        checked_at = float(state["checkedAt"])
        result = state["result"]
        fingerprint = state["configFingerprint"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError("usage guard cache is invalid or unreadable") from error
    if fingerprint != config_fingerprint:
        return None
    _decision_message(result)
    if result.get("decision") == "block" and result.get("blockedUntil"):
        blocked_until = check_usage._reset_instant(
            result["blockedUntil"], "blockedUntil"
        ).timestamp()
        if now >= blocked_until:
            return None
    if 0 <= now - checked_at < interval:
        return result
    return None


def _write_cached(
    path: Path,
    now: float,
    config_fingerprint: str,
    result: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "checkedAt": now,
                    "configFingerprint": config_fingerprint,
                    "result": result,
                },
                handle,
            )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _decision_message(result: dict[str, Any]) -> str:
    if result.get("error"):
        return f"Codex usage guard failed closed: {result['error']}"
    if result.get("decision") not in {"allow", "warn", "block"}:
        raise ValueError("usage guard decision is invalid")
    windows = result["windows"]
    thresholds = result["thresholds"]
    label = result.get("projectLabel") or "Codex work"
    summaries: list[str] = []
    if "primary" in windows:
        summaries.extend(
            [
                f"primary={windows['primary']['usedPercent']:g}%",
                f"primary hard limit={thresholds['primary']['hardPercent']:g}%",
            ]
        )
    summaries.extend(
        [
            f"weekly={windows['secondary']['usedPercent']:g}%",
            f"weekly hard limit={thresholds['secondary']['hardPercent']:g}%",
        ]
    )
    message = f"{label} Codex usage guard: " + ", ".join(summaries)
    reserve = result.get("reserveLabel")
    if reserve:
        message += f", reserve for {reserve}"
    if result.get("blockedUntil"):
        message += f", blocked until {result['blockedUntil']}"
    return message


def _is_resume_coordination_tool(tool_name: str | None) -> bool:
    return isinstance(tool_name, str) and (
        tool_name == "automation_update" or tool_name.endswith("__automation_update")
    )


def _hook_output(
    event: str,
    result: dict[str, Any],
    tool_name: str | None = None,
) -> dict[str, Any] | None:
    decision = result.get("decision")
    message = _decision_message(result)
    if decision == "block":
        instruction = result.get("blockInstruction")
        if instruction:
            message += f"; {instruction}"
        if event == "PreToolUse":
            if _is_resume_coordination_tool(tool_name):
                return None
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": message,
                }
            }
        return {
            "hookSpecificOutput": {
                "hookEventName": event,
                "additionalContext": (
                    message
                    + "; do not continue expensive work; preserve resumable state and arrange or refresh the guard-resume heartbeat."
                ),
            }
        }
    if decision == "warn":
        instruction = result.get("warnInstruction")
        suffix = (
            f"; {instruction}"
            if instruction
            else "; finish only the current bounded phase, avoid new speculative work or delegation, and recheck before another expensive phase."
        )
        return {
            "hookSpecificOutput": {
                "hookEventName": event,
                "additionalContext": message + suffix,
            }
        }
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="Read a codexbar JSON fixture")
    parser.add_argument("--config", help="Use a specific usage-guard JSON config")
    parser.add_argument("--state-dir", default=str(_default_state_dir()))
    parser.add_argument("--now", type=float, default=None)
    parser.add_argument("--interval-seconds", type=int, default=None)
    args = parser.parse_args()

    try:
        hook_input = json.loads(sys.stdin.read())
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"invalid hook input: {error}", file=sys.stderr)
        return 2
    event = hook_input.get("hook_event_name") if isinstance(hook_input, dict) else None
    session_id = hook_input.get("session_id") if isinstance(hook_input, dict) else None
    cwd = hook_input.get("cwd") if isinstance(hook_input, dict) else None
    tool_name = hook_input.get("tool_name") if isinstance(hook_input, dict) else None
    if event not in VALID_EVENTS or not isinstance(session_id, str) or not session_id:
        print("invalid hook input: event or session_id is missing", file=sys.stderr)
        return 2
    if cwd is not None and not isinstance(cwd, str):
        print("invalid hook input: cwd must be a string", file=sys.stderr)
        return 2
    if event == "PreToolUse" and not isinstance(tool_name, str):
        print("invalid hook input: tool_name must be a string", file=sys.stderr)
        return 2

    now = args.now if args.now is not None else time.time()
    state_path = _state_path(Path(args.state_dir), session_id)
    try:
        config = check_usage.load_config(cwd, args.config)
        interval = args.interval_seconds or config["recheckSeconds"]
        if interval <= 0:
            raise ValueError("interval-seconds must be positive")
        fingerprint = _config_fingerprint(config)
        result = _load_cached(state_path, now, interval, fingerprint)
        if result is None:
            result = check_usage.evaluate_usage(
                check_usage.read_payload(args.input), config, now=now
            )
            _write_cached(state_path, now, fingerprint, result)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, json.JSONDecodeError) as error:
        result = {"decision": "block", "error": str(error)}

    output = _hook_output(event, result, tool_name)
    if output is not None:
        print(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
