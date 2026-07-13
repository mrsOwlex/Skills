#!/usr/bin/env python3
"""Evaluate configurable Codex five-hour and weekly usage gates."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXIT_BLOCKED = 75
EXIT_ERROR = 2
CODEXBAR_TIMEOUT_SECONDS = 10
DEFAULT_CONFIG = {
    "projectLabel": "Codex work",
    "reserveLabel": None,
    "warnInstruction": None,
    "blockInstruction": None,
    "recheckSeconds": 900,
    "windows": {
        "primary": {
            "warningPercent": 80.0,
            "hardPercent": 90.0,
            "paceMinimumPercent": 50.0,
        },
        "secondary": {
            "warningPercent": 70.0,
            "hardPercent": 80.0,
            "paceMinimumPercent": 70.0,
        },
    },
}
CONFIG_KEYS = {
    "projectLabel",
    "reserveLabel",
    "warnInstruction",
    "blockInstruction",
    "recheckSeconds",
    "windows",
}
WINDOW_KEYS = {"warningPercent", "hardPercent", "paceMinimumPercent"}


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _label(value: Any, name: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def validate_config(value: Any, *, source: str | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("usage guard config must be an object")
    unknown = sorted(set(value) - CONFIG_KEYS)
    if unknown:
        raise ValueError(f"usage guard config has unknown fields: {', '.join(unknown)}")
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if "projectLabel" in value:
        config["projectLabel"] = _label(value["projectLabel"], "projectLabel")
    if "reserveLabel" in value:
        config["reserveLabel"] = _label(value["reserveLabel"], "reserveLabel", optional=True)
    for instruction in ("warnInstruction", "blockInstruction"):
        if instruction in value:
            config[instruction] = _label(value[instruction], instruction, optional=True)
    if "recheckSeconds" in value:
        interval = value["recheckSeconds"]
        if isinstance(interval, bool) or not isinstance(interval, int) or not 60 <= interval <= 86_400:
            raise ValueError("recheckSeconds must be an integer from 60 to 86400")
        config["recheckSeconds"] = interval
    if "windows" in value:
        windows = value["windows"]
        if not isinstance(windows, dict):
            raise ValueError("windows must be an object")
        unknown_windows = sorted(set(windows) - {"primary", "secondary"})
        if unknown_windows:
            raise ValueError(f"windows has unknown fields: {', '.join(unknown_windows)}")
        for name, raw in windows.items():
            if not isinstance(raw, dict):
                raise ValueError(f"windows.{name} must be an object")
            unknown_fields = sorted(set(raw) - WINDOW_KEYS)
            if unknown_fields:
                raise ValueError(f"windows.{name} has unknown fields: {', '.join(unknown_fields)}")
            for key, raw_value in raw.items():
                config["windows"][name][key] = _finite_number(raw_value, f"windows.{name}.{key}")
    for name, threshold in config["windows"].items():
        pace = threshold["paceMinimumPercent"]
        warning = threshold["warningPercent"]
        hard = threshold["hardPercent"]
        if not 0 <= pace <= 100 or not 0 <= warning <= hard <= 100:
            raise ValueError(
                f"{name} thresholds must satisfy 0 <= pace minimum <= 100 and "
                "0 <= warning <= hard <= 100"
            )
    config["configPath"] = source
    return config


def discover_config(start_directory: str | Path | None = None, explicit: str | None = None) -> Path | None:
    selected = explicit or os.environ.get("CODEX_USAGE_GUARD_CONFIG")
    if selected:
        return Path(selected).expanduser().resolve()
    start = Path(start_directory or Path.cwd()).expanduser().resolve()
    if start.is_file():
        start = start.parent
    for directory in (start, *start.parents):
        candidate = directory / ".codex" / "usage-guard.json"
        if candidate.is_file():
            return candidate
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    global_candidate = codex_home / "usage-guard.json"
    return global_candidate.resolve() if global_candidate.is_file() else None


def load_config(start_directory: str | Path | None = None, explicit: str | None = None) -> dict[str, Any]:
    path = discover_config(start_directory, explicit)
    if path is None:
        return validate_config({})
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"usage guard config does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"usage guard config is invalid JSON: {path}") from error
    return validate_config(raw, source=str(path))


def _codex_record(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, list):
        raise ValueError("codexbar output must be a JSON array")
    for item in payload:
        if isinstance(item, dict) and item.get("provider") == "codex":
            return item
    raise ValueError("codex usage record is missing")


def _reset_instant(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"codex {name}.resetsAt is missing")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"codex {name}.resetsAt is invalid") from error
    if instant.tzinfo is None:
        raise ValueError(f"codex {name}.resetsAt must include a timezone")
    return instant


def _evaluation_instant(value: datetime | float | int | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("evaluation time must include a timezone")
        return value
    timestamp = _finite_number(value, "evaluation time")
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def _window(record: dict[str, Any], name: str) -> dict[str, Any]:
    usage = record.get("usage")
    if not isinstance(usage, dict) or not isinstance(usage.get(name), dict):
        raise ValueError(f"codex {name} usage window is missing")
    window = usage[name]
    used = _finite_number(window.get("usedPercent"), f"codex {name}.usedPercent")
    if not 0 <= used <= 100:
        raise ValueError(f"codex {name}.usedPercent must be from 0 to 100")
    resets_at = window.get("resetsAt")
    _reset_instant(resets_at, name)
    return {"usedPercent": used, "resetsAt": resets_at}


def evaluate_usage(
    payload: Any,
    config: dict[str, Any] | None = None,
    *,
    now: datetime | float | int | None = None,
) -> dict[str, Any]:
    effective = validate_config({}) if config is None else validate_config(
        {key: value for key, value in config.items() if key != "configPath"},
        source=config.get("configPath"),
    )
    record = _codex_record(payload)
    usage = record.get("usage")
    if not isinstance(usage, dict):
        raise ValueError("codex usage data must be an object")
    windows: dict[str, dict[str, Any]] = {}
    unavailable_windows: list[str] = []
    if usage.get("primary") is not None:
        windows["primary"] = _window(record, "primary")
    else:
        unavailable_windows.append("primary")
    windows["secondary"] = _window(record, "secondary")
    reasons: list[str] = []
    blocking: list[str] = []
    for name, window in windows.items():
        threshold = effective["windows"][name]
        if window["usedPercent"] >= threshold["hardPercent"]:
            blocking.append(name)
            reasons.append(f"{name}-hard-limit")
        elif window["usedPercent"] >= threshold["warningPercent"]:
            reasons.append(f"{name}-warning-limit")
    pace = record.get("pace", {})
    if not isinstance(pace, dict):
        raise ValueError("codex pace data must be an object")
    unavailable: list[str] = []
    for name in ("primary", "secondary"):
        if name not in pace:
            if name in windows:
                unavailable.append(name)
            continue
        projection = pace[name]
        if not isinstance(projection, dict):
            raise ValueError(f"codex {name} pace data must be an object")
        will_last = projection.get("willLastToReset")
        if not isinstance(will_last, bool):
            raise ValueError(f"codex {name} pace.willLastToReset must be boolean")
        floor = effective["windows"][name]["paceMinimumPercent"]
        if name in windows and not will_last and windows[name]["usedPercent"] >= floor:
            reasons.append(f"{name}-pace")
    decision = "block" if blocking else "warn" if reasons else "allow"
    blocked_until = None
    if blocking:
        latest = max(blocking, key=lambda name: _reset_instant(windows[name]["resetsAt"], name))
        blocked_until = windows[latest]["resetsAt"]
        if _reset_instant(blocked_until, "blockedUntil") <= _evaluation_instant(now):
            raise ValueError("codex blockedUntil must be in the future")
    return {
        "decision": decision,
        "projectLabel": effective["projectLabel"],
        "reserveLabel": effective["reserveLabel"],
        "warnInstruction": effective["warnInstruction"],
        "blockInstruction": effective["blockInstruction"],
        "configPath": effective["configPath"],
        "recheckSeconds": effective["recheckSeconds"],
        "thresholds": effective["windows"],
        "windows": windows,
        "reasons": reasons,
        "blockingWindows": blocking,
        "blockedUntil": blocked_until,
        "unavailableWindows": unavailable_windows,
        "paceUnavailable": unavailable,
    }


def read_payload(input_path: str | None) -> Any:
    if input_path:
        return json.loads(Path(input_path).read_text(encoding="utf-8"))
    try:
        result = subprocess.run(
            ["codexbar", "usage", "--provider", "codex", "--format", "json", "--pretty"],
            capture_output=True,
            text=True,
            check=False,
            timeout=CODEXBAR_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"codexbar usage timed out after {CODEXBAR_TIMEOUT_SECONDS} seconds") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit code {result.returncode}"
        raise RuntimeError(f"codexbar usage failed: {detail}")
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="Read a codexbar JSON fixture")
    parser.add_argument("--config", help="Use a specific usage-guard JSON config")
    parser.add_argument("--cwd", help="Start config discovery from this directory")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        config = load_config(args.cwd, args.config)
        result = evaluate_usage(read_payload(args.input), config)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"ERROR | {error}", file=sys.stderr)
        return EXIT_ERROR
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        weekly = result["windows"]["secondary"]["usedPercent"]
        primary = result["windows"].get("primary")
        if primary is None:
            print(f"{result['decision'].upper()} | weekly={weekly:g}%")
        else:
            print(
                f"{result['decision'].upper()} | primary={primary['usedPercent']:g}% "
                f"| weekly={weekly:g}%"
            )
    return EXIT_BLOCKED if result["decision"] == "block" else 0


if __name__ == "__main__":
    raise SystemExit(main())
