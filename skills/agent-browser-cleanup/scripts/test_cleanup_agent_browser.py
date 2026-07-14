#!/usr/bin/env python3
"""Tests for cleanup_agent_browser.py using a fake agent-browser CLI."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
CLEANUP_SCRIPT = SCRIPT_DIR / "cleanup_agent_browser.py"


FAKE_CLI = r'''#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

args = sys.argv[1:]
Path(os.environ["FAKE_LOG"]).write_text(
    json.dumps(json.loads(Path(os.environ["FAKE_LOG"]).read_text()) + [args])
)
scenario = os.environ["FAKE_SCENARIO"]

if scenario == "close-fails" and args == ["close", "--all", "--json"]:
    print("close failed", file=sys.stderr)
    raise SystemExit(7)

if args == ["close", "--all", "--json"]:
    if scenario == "hang":
        time.sleep(2)
    if scenario == "remaining-sessions":
        print(json.dumps({"success": True, "data": {"closed": 1, "sessions": ["stuck"]}}))
    elif scenario == "partial-close":
        print(json.dumps({"success": True, "data": {"closed": 1, "failed": ["stuck"]}}))
    else:
        print(json.dumps({"success": True, "data": {"closed": 2, "sessions": []}}))
    raise SystemExit(0)

if len(args) == 5 and args[0] == "--session" and args[2:] == ["session", "info", "--json"]:
    launched = scenario != "remote-session"
    print(json.dumps({
        "success": True,
        "data": {
            "runtime": {
                "browserLaunched": launched,
                "effectiveLaunch": {"browserLaunched": launched},
            }
        },
    }))
    raise SystemExit(0)

if args == ["session", "list", "--json"]:
    previous_calls = json.loads(Path(os.environ["FAKE_LOG"]).read_text())
    session_list_calls = sum(call == args for call in previous_calls)
    if scenario == "remaining-sessions":
        sessions = ["stuck"]
    elif scenario == "remote-session":
        sessions = ["remote"]
    elif scenario == "eventually-empty":
        sessions = ["default"] if session_list_calls == 1 else ["stopping"] if session_list_calls == 2 else []
    else:
        sessions = []
    print(json.dumps({"success": True, "data": {"sessions": sessions}}))
    raise SystemExit(0)

if args == ["doctor", "--offline", "--quick", "--json"]:
    previous_calls = json.loads(Path(os.environ["FAKE_LOG"]).read_text())
    doctor_calls = sum(call == args for call in previous_calls)
    daemon_status = "warn" if scenario == "daemon-stopping" and doctor_calls == 1 else "pass"
    print(json.dumps({
        "success": True,
        "checks": [{
            "id": "daemon.active",
            "status": daemon_status,
            "message": "Daemon stopping" if daemon_status == "warn" else "No active daemons",
        }],
    }))
    raise SystemExit(0)

print(json.dumps({"success": False, "error": "unexpected arguments", "args": args}))
raise SystemExit(9)
'''


class CleanupAgentBrowserTests(unittest.TestCase):
    def run_cleanup(
        self,
        scenario: str,
        *options: str,
        namespace: str | None = "test-agent-browser",
    ) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            fake_cli = temporary / "agent-browser"
            fake_cli.write_text(FAKE_CLI)
            fake_cli.chmod(fake_cli.stat().st_mode | stat.S_IXUSR)

            log_file = temporary / "calls.json"
            log_file.write_text("[]")
            environment = os.environ.copy()
            environment.update(
                {
                    "FAKE_LOG": str(log_file),
                    "FAKE_SCENARIO": scenario,
                }
            )
            if namespace is None:
                environment.pop("AGENT_BROWSER_NAMESPACE", None)
            else:
                environment["AGENT_BROWSER_NAMESPACE"] = namespace
            result = subprocess.run(
                [
                    sys.executable,
                    str(CLEANUP_SCRIPT),
                    "--cli",
                    str(fake_cli),
                    "--wait-seconds",
                    "0",
                    *options,
                ],
                env=environment,
                capture_output=True,
                text=True,
            )
            calls = json.loads(log_file.read_text())
            return result, calls

    def test_closes_all_sessions_and_verifies_daemon(self) -> None:
        result, calls = self.run_cleanup("success")

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["closed"], 2)
        self.assertEqual(report["sessions"], [])
        self.assertEqual(calls, [
            ["session", "list", "--json"],
            ["close", "--all", "--json"],
            ["session", "list", "--json"],
            ["doctor", "--offline", "--quick", "--json"],
        ])

    def test_waits_for_asynchronous_session_shutdown(self) -> None:
        result, calls = self.run_cleanup(
            "eventually-empty",
            "--wait-seconds",
            "1",
            "--poll-interval",
            "0.01",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])
        self.assertGreaterEqual(calls.count(["session", "list", "--json"]), 3)

    def test_fails_when_a_session_remains(self) -> None:
        result, calls = self.run_cleanup("remaining-sessions")

        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stderr)
        self.assertFalse(report["ok"])
        self.assertEqual(report["step"], "verify-sessions")
        self.assertEqual(report["sessions"], ["stuck"])
        self.assertEqual(calls, [
            ["session", "list", "--json"],
            ["--session", "stuck", "session", "info", "--json"],
            ["close", "--all", "--json"],
            ["session", "list", "--json"],
        ])

    def test_reports_close_failure_without_running_destructive_fallbacks(self) -> None:
        result, calls = self.run_cleanup("close-fails")

        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stderr)
        self.assertFalse(report["ok"])
        self.assertEqual(report["step"], "close")
        self.assertEqual(calls, [
            ["session", "list", "--json"],
            ["close", "--all", "--json"],
        ])

    def test_reports_partial_close_as_failure(self) -> None:
        result, calls = self.run_cleanup("partial-close")

        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stderr)
        self.assertFalse(report["ok"])
        self.assertEqual(report["step"], "close")
        self.assertEqual(report["failed"], ["stuck"])
        self.assertEqual(calls, [
            ["session", "list", "--json"],
            ["close", "--all", "--json"],
        ])

    def test_polls_until_daemon_is_inactive(self) -> None:
        result, calls = self.run_cleanup(
            "daemon-stopping",
            "--wait-seconds",
            "1",
            "--poll-interval",
            "0.01",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])
        self.assertGreaterEqual(calls.count(["doctor", "--offline", "--quick", "--json"]), 2)

    def test_requires_an_isolated_namespace(self) -> None:
        result, calls = self.run_cleanup("success", namespace="default")

        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stderr)
        self.assertEqual(report["step"], "namespace")
        self.assertEqual(calls, [])

    def test_reports_hung_cli_command_as_timeout(self) -> None:
        result, calls = self.run_cleanup(
            "hang",
            "--command-timeout-seconds",
            "0.5",
        )

        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stderr)
        self.assertEqual(report["step"], "close")
        self.assertEqual(report["timeoutSeconds"], 0.5)
        self.assertEqual(calls, [
            ["session", "list", "--json"],
            ["close", "--all", "--json"],
        ])

    def test_refuses_a_session_without_local_launch_evidence(self) -> None:
        result, calls = self.run_cleanup("remote-session")

        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stderr)
        self.assertEqual(report["step"], "verify-ownership")
        self.assertEqual(report["session"], "remote")
        self.assertEqual(calls, [
            ["session", "list", "--json"],
            ["--session", "remote", "session", "info", "--json"],
        ])

    def test_rejects_non_finite_wait_values(self) -> None:
        result, calls = self.run_cleanup("success", "--wait-seconds", "inf")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)["step"], "arguments")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
