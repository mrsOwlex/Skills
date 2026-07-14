#!/usr/bin/env python3
"""Close agent-browser sessions and verify that its local daemon is gone."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence


@dataclass(frozen=True)
class Invocation:
    """Result of one bounded agent-browser CLI invocation."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    timeout_seconds: float | None = None
    start_error: bool = False


def compact_output(value: str, limit: int = 1000) -> str:
    """Keep diagnostics useful without dumping arbitrary command output."""

    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def failure_report(step: str, message: str, **details: Any) -> dict[str, Any]:
    report: dict[str, Any] = {"ok": False, "step": step, "error": message}
    report.update(details)
    return report


def emit_failure(report: dict[str, Any]) -> int:
    json.dump(report, sys.stderr, ensure_ascii=False, sort_keys=True)
    sys.stderr.write("\n")
    return 1


def failure(step: str, message: str, **details: Any) -> int:
    return emit_failure(failure_report(step, message, **details))


def resolve_cli(requested: str) -> str | None:
    """Resolve a command name or executable path without invoking a shell."""

    if Path(requested).name != requested or "/" in requested:
        path = Path(requested).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        return None
    return shutil.which(requested)


def invoke(cli: str, arguments: Sequence[str], timeout_seconds: float) -> Invocation:
    """Run one CLI command with a hard timeout and no shell interpretation."""

    try:
        result = subprocess.run(
            [cli, *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return Invocation(
            returncode=124,
            stdout=as_text(exc.stdout),
            stderr=as_text(exc.stderr),
            timed_out=True,
            timeout_seconds=timeout_seconds,
        )
    except OSError as exc:
        return Invocation(
            returncode=126,
            stdout="",
            stderr=str(exc),
            start_error=True,
        )

    return Invocation(
        returncode=result.returncode,
        stdout=as_text(result.stdout),
        stderr=as_text(result.stderr),
    )


def read_success_payload(
    result: Invocation,
    step: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Parse a successful JSON CLI response without emitting a premature error."""

    if result.timed_out:
        return None, failure_report(
            step,
            "agent-browser command timed out",
            timeoutSeconds=result.timeout_seconds,
            stderr=compact_output(result.stderr),
        )
    if result.returncode != 0:
        return None, failure_report(
            step,
            "agent-browser command could not be started"
            if result.start_error
            else "agent-browser command failed",
            returncode=result.returncode,
            stderr=compact_output(result.stderr),
        )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return None, failure_report(
            step,
            "agent-browser returned invalid JSON",
            detail=str(exc),
            stdout=compact_output(result.stdout),
        )

    if not isinstance(payload, dict) or payload.get("success") is not True:
        return None, failure_report(
            step,
            "agent-browser reported failure",
            response=payload,
        )
    return payload, None


def read_sessions(
    cli: str,
    timeout_seconds: float,
) -> tuple[list[str] | None, dict[str, Any] | None]:
    result = invoke(cli, ["session", "list", "--json"], timeout_seconds)
    payload, problem = read_success_payload(result, "verify-sessions")
    if problem is not None:
        return None, problem
    assert payload is not None

    data = payload.get("data")
    sessions_value = data.get("sessions") if isinstance(data, dict) else None
    if not isinstance(sessions_value, list) or not all(
        isinstance(session, str) and session for session in sessions_value
    ):
        return None, failure_report(
            "verify-sessions",
            "agent-browser session list has no valid sessions array",
        )
    return sessions_value, None


def verify_local_session(
    cli: str,
    session: str,
    timeout_seconds: float,
) -> dict[str, Any] | None:
    """Refuse sessions without evidence that agent-browser launched the browser."""

    result = invoke(
        cli,
        ["--session", session, "session", "info", "--json"],
        timeout_seconds,
    )
    payload, problem = read_success_payload(result, "verify-ownership")
    if problem is not None:
        return problem
    assert payload is not None

    data = payload.get("data")
    runtime = data.get("runtime") if isinstance(data, dict) else None
    effective_launch = runtime.get("effectiveLaunch") if isinstance(runtime, dict) else None
    launched = (
        isinstance(runtime, dict) and runtime.get("browserLaunched") is True
    ) or (
        isinstance(effective_launch, dict)
        and effective_launch.get("browserLaunched") is True
    )
    if not launched:
        return failure_report(
            "verify-ownership",
            "refusing to close a session without local browser-launch evidence",
            session=session,
        )
    return None


def read_daemon_check(
    cli: str,
    timeout_seconds: float,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    result = invoke(
        cli,
        ["doctor", "--offline", "--quick", "--json"],
        timeout_seconds,
    )
    payload, problem = read_success_payload(result, "verify-daemon")
    if problem is not None:
        return None, problem
    assert payload is not None

    checks = payload.get("checks")
    daemon_check = next(
        (
            check
            for check in checks
            if isinstance(check, dict) and check.get("id") == "daemon.active"
        ),
        None,
    ) if isinstance(checks, list) else None
    if not isinstance(daemon_check, dict):
        return None, failure_report(
            "verify-daemon",
            "agent-browser doctor returned no daemon.active check",
        )
    return daemon_check, None


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Close all agent-browser sessions in an isolated namespace and verify cleanup."
    )
    parser.add_argument(
        "--cli",
        default=os.environ.get("AGENT_BROWSER_CLI", "agent-browser"),
        help="agent-browser executable or command name (default: agent-browser)",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=10.0,
        help="maximum time to wait for asynchronous shutdown (default: 10)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.25,
        help="delay between shutdown checks in seconds (default: 0.25)",
    )
    parser.add_argument(
        "--command-timeout-seconds",
        type=float,
        default=5.0,
        help="maximum runtime for each agent-browser command (default: 5)",
    )
    return parser.parse_args()


def sleep_until(deadline: float, poll_interval: float) -> bool:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return False
    time.sleep(min(poll_interval, remaining))
    return True


def main() -> int:
    arguments = parse_arguments()
    if (
        not math.isfinite(arguments.wait_seconds)
        or not math.isfinite(arguments.poll_interval)
        or arguments.wait_seconds < 0
        or arguments.poll_interval <= 0
    ):
        return failure(
            "arguments",
            "wait-seconds and poll-interval must be finite; wait-seconds must be non-negative and poll-interval must be positive",
        )
    if not math.isfinite(arguments.command_timeout_seconds) or arguments.command_timeout_seconds <= 0:
        return failure(
            "arguments",
            "command-timeout-seconds must be finite and positive",
        )

    namespace = os.environ.get("AGENT_BROWSER_NAMESPACE", "").strip()
    if not namespace:
        return failure(
            "namespace",
            "AGENT_BROWSER_NAMESPACE must name an isolated agent namespace",
        )
    if namespace == "default":
        return failure(
            "namespace",
            "refusing the shared default namespace; set a unique AGENT_BROWSER_NAMESPACE",
            namespace=namespace,
        )

    cli = resolve_cli(arguments.cli)
    if cli is None:
        return failure(
            "resolve-cli",
            "agent-browser executable was not found or is not executable",
            requested=arguments.cli,
        )

    # Inspect ownership before close --all so a personal CDP/auto-connect session
    # cannot be mistaken for a browser launched by this agent.
    active_sessions, problem = read_sessions(cli, arguments.command_timeout_seconds)
    if problem is not None:
        return emit_failure(problem)
    assert active_sessions is not None
    for session in active_sessions:
        problem = verify_local_session(cli, session, arguments.command_timeout_seconds)
        if problem is not None:
            return emit_failure(problem)

    close_result = invoke(
        cli,
        ["close", "--all", "--json"],
        arguments.command_timeout_seconds,
    )
    close_payload, problem = read_success_payload(close_result, "close")
    if problem is not None:
        return emit_failure(problem)
    assert close_payload is not None

    close_data = close_payload.get("data")
    if not isinstance(close_data, dict):
        return failure("close", "agent-browser close response has no data object")
    failed = close_data.get("failed", [])
    if failed:
        return failure(
            "close",
            "agent-browser reported sessions that could not be closed",
            failed=failed,
        )
    closed = close_data.get("closed", 0)
    if not isinstance(closed, int) or isinstance(closed, bool):
        return failure("close", "agent-browser close response has an invalid closed count")

    deadline = time.monotonic() + arguments.wait_seconds
    sessions: list[str] = []
    while True:
        sessions, problem = read_sessions(cli, arguments.command_timeout_seconds)
        if problem is not None:
            if not sleep_until(deadline, arguments.poll_interval):
                return emit_failure(problem)
            continue
        assert sessions is not None
        if not sessions:
            break
        if not sleep_until(deadline, arguments.poll_interval):
            return failure(
                "verify-sessions",
                "agent-browser sessions remain after cleanup",
                sessions=sessions,
            )

    daemon_check: dict[str, Any] | None = None
    while True:
        daemon_check, problem = read_daemon_check(cli, arguments.command_timeout_seconds)
        if problem is not None:
            if not sleep_until(deadline, arguments.poll_interval):
                return emit_failure(problem)
            continue
        assert daemon_check is not None
        if daemon_check.get("status") == "pass":
            break
        if not sleep_until(deadline, arguments.poll_interval):
            return failure(
                "verify-daemon",
                "agent-browser daemon is still active or could not be verified",
                check=daemon_check,
            )

    report = {
        "ok": True,
        "closed": closed,
        "sessions": [],
        "daemon": {
            "status": daemon_check.get("status"),
            "message": daemon_check.get("message"),
        },
        "namespace": namespace,
    }
    json.dump(report, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
