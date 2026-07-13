#!/usr/bin/env python3
"""Regression tests for the global Codex usage guard."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


SCRIPTS_DIR = Path(__file__).parent
CHECK_SCRIPT = SCRIPTS_DIR / "check_usage.py"
HOOK_SCRIPT = SCRIPTS_DIR / "usage_guard_hook.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_payload(*, primary=22, secondary=9, primary_pace=True, secondary_pace=True):
    return [{
        "provider": "codex",
        "pace": {
            "primary": {"willLastToReset": primary_pace},
            "secondary": {"willLastToReset": secondary_pace},
        },
        "usage": {
            "primary": {"usedPercent": primary, "resetsAt": "2099-07-12T02:27:24Z"},
            "secondary": {"usedPercent": secondary, "resetsAt": "2099-07-18T06:06:22Z"},
        },
    }]


class DecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = load_module(CHECK_SCRIPT, "global_check_usage")

    def test_absolute_thresholds_warn_and_block_separately(self):
        self.assertEqual(self.guard.evaluate_usage(sample_payload(primary=80))["decision"], "warn")
        blocked = self.guard.evaluate_usage(sample_payload(secondary=80))
        self.assertEqual(blocked["decision"], "block")
        self.assertEqual(blocked["blockedUntil"], "2099-07-18T06:06:22Z")

    def test_pace_is_ignored_below_each_configured_floor(self):
        below = self.guard.evaluate_usage(sample_payload(primary=49.9, secondary=69.9, primary_pace=False, secondary_pace=False))
        self.assertEqual(below["decision"], "allow")
        at_floor = self.guard.evaluate_usage(sample_payload(primary=50, secondary=70, primary_pace=False, secondary_pace=False))
        self.assertEqual(at_floor["decision"], "warn")
        self.assertIn("primary-pace", at_floor["reasons"])
        self.assertIn("secondary-pace", at_floor["reasons"])

    def test_missing_pace_is_allowed_but_malformed_pace_fails(self):
        payload = sample_payload()
        del payload[0]["pace"]
        result = self.guard.evaluate_usage(payload)
        self.assertEqual(result["decision"], "allow")
        self.assertEqual(result["paceUnavailable"], ["primary", "secondary"])
        malformed = sample_payload()
        malformed[0]["pace"]["primary"]["willLastToReset"] = "yes"
        with self.assertRaisesRegex(ValueError, "must be boolean"):
            self.guard.evaluate_usage(malformed)

    def test_custom_config_changes_thresholds_and_labels(self):
        config = self.guard.validate_config({
            "projectLabel": "Low priority",
            "reserveLabel": "Operations",
            "warnInstruction": "Notify the operator and finish the phase.",
            "blockInstruction": "Notify the operator and wait for reset.",
            "windows": {
                "primary": {"paceMinimumPercent": 20, "warningPercent": 30, "hardPercent": 40},
                "secondary": {"paceMinimumPercent": 25, "warningPercent": 35, "hardPercent": 45},
            },
        })
        result = self.guard.evaluate_usage(sample_payload(primary=40), config)
        self.assertEqual(result["decision"], "block")
        self.assertEqual(result["projectLabel"], "Low priority")
        self.assertEqual(result["reserveLabel"], "Operations")
        self.assertEqual(result["blockInstruction"], "Notify the operator and wait for reset.")

    def test_equal_warning_and_hard_thresholds_are_supported(self):
        config = self.guard.validate_config({
            "windows": {
                "primary": {
                    "paceMinimumPercent": 80,
                    "warningPercent": 80,
                    "hardPercent": 80,
                },
            },
        })
        result = self.guard.evaluate_usage(sample_payload(primary=80), config)
        self.assertEqual(result["decision"], "block")
        self.assertEqual(result["reasons"], ["primary-hard-limit"])

    def test_pace_floor_can_exceed_warning_threshold(self):
        config = self.guard.validate_config({
            "windows": {
                "primary": {
                    "paceMinimumPercent": 80,
                    "warningPercent": 50,
                    "hardPercent": 90,
                },
            },
        })
        result = self.guard.evaluate_usage(
            sample_payload(primary=60, primary_pace=False),
            config,
        )
        self.assertEqual(result["reasons"], ["primary-warning-limit"])

    def test_expired_blocked_until_is_rejected(self):
        payload = sample_payload(primary=95)
        payload[0]["usage"]["primary"]["resetsAt"] = "2026-07-12T02:27:24Z"
        with self.assertRaisesRegex(ValueError, "blockedUntil must be in the future"):
            self.guard.evaluate_usage(
                payload,
                now=datetime(2026, 7, 13, tzinfo=timezone.utc),
            )

    def test_missing_primary_window_uses_weekly_window(self):
        payload = sample_payload(secondary=80)
        del payload[0]["usage"]["primary"]
        del payload[0]["pace"]["primary"]
        result = self.guard.evaluate_usage(payload)
        self.assertEqual(result["decision"], "block")
        self.assertEqual(result["windows"], {
            "secondary": {
                "usedPercent": 80.0,
                "resetsAt": "2099-07-18T06:06:22Z",
            },
        })
        self.assertEqual(result["unavailableWindows"], ["primary"])
        self.assertEqual(result["blockedUntil"], "2099-07-18T06:06:22Z")

    def test_invalid_config_and_usage_fail_closed_at_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            fixture = root / "usage.json"
            config.write_text('{"windows":{"primary":{"warningPercent":95,"hardPercent":90}}}', encoding="utf-8")
            fixture.write_text(json.dumps(sample_payload()), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(CHECK_SCRIPT), "--config", str(config), "--input", str(fixture), "--json"],
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("thresholds", result.stderr)


class ConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = load_module(CHECK_SCRIPT, "global_check_config")

    def test_discovers_nearest_project_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "a" / "b"
            nested.mkdir(parents=True)
            config_dir = root / ".codex"
            config_dir.mkdir()
            path = config_dir / "usage-guard.json"
            path.write_text('{"projectLabel":"Nearest"}', encoding="utf-8")
            loaded = self.guard.load_config(nested)
        self.assertEqual(loaded["projectLabel"], "Nearest")
        self.assertEqual(loaded["configPath"], str(path.resolve()))

    def test_unknown_fields_and_bad_intervals_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            self.guard.validate_config({"warnPercent": 80})
        with self.assertRaisesRegex(ValueError, "recheckSeconds"):
            self.guard.validate_config({"recheckSeconds": 10})


class HookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SCRIPTS_DIR))
        cls.hook = load_module(HOOK_SCRIPT, "global_usage_hook")

    def run_hook(
        self,
        *,
        fixture,
        config,
        state_dir,
        now,
        session="s1",
        event="PreToolUse",
        tool_name="Bash",
    ):
        root = Path(state_dir)
        fixture_path = root / f"usage-{now}.json"
        config_path = root / "config.json"
        fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
        config_path.write_text(json.dumps(config), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(HOOK_SCRIPT), "--input", str(fixture_path), "--config", str(config_path), "--state-dir", str(root / "state"), "--now", str(now)],
            input=json.dumps({"session_id": session, "cwd": str(root), "hook_event_name": event, "tool_name": tool_name}),
            capture_output=True, text=True, check=False,
        )

    def test_cached_block_remains_until_recheck(self):
        with tempfile.TemporaryDirectory() as directory:
            first = self.run_hook(fixture=sample_payload(primary=95), config={}, state_dir=directory, now=1000)
            cached = self.run_hook(fixture=sample_payload(), config={}, state_dir=directory, now=1100)
        self.assertEqual(json.loads(first.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(json.loads(cached.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_cached_block_expires_at_blocked_until(self):
        blocked_fixture = sample_payload(primary=95)
        blocked_fixture[0]["usage"]["primary"]["resetsAt"] = "1970-01-01T00:20:00Z"
        with tempfile.TemporaryDirectory() as directory:
            first = self.run_hook(
                fixture=blocked_fixture,
                config={},
                state_dir=directory,
                now=1000,
                session="reset-boundary",
            )
            refreshed = self.run_hook(
                fixture=sample_payload(),
                config={},
                state_dir=directory,
                now=1200,
                session="reset-boundary",
            )
        self.assertEqual(json.loads(first.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(refreshed.stdout, "")

    def test_config_change_invalidates_session_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            first = self.run_hook(fixture=sample_payload(primary=50), config={}, state_dir=directory, now=1000)
            changed = self.run_hook(
                fixture=sample_payload(primary=50),
                config={"windows": {"primary": {"paceMinimumPercent": 10, "warningPercent": 20, "hardPercent": 40}}},
                state_dir=directory, now=1100,
            )
        self.assertEqual(first.stdout, "")
        self.assertEqual(json.loads(changed.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_data_error_blocks_and_warn_has_bounded_phase_context(self):
        with tempfile.TemporaryDirectory() as directory:
            error = self.run_hook(fixture=[], config={}, state_dir=directory, now=1000, session="error")
            warn = self.run_hook(fixture=sample_payload(primary=80), config={}, state_dir=directory, now=1000, session="warn", event="SessionStart")
        self.assertEqual(json.loads(error.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")
        context = json.loads(warn.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("current bounded phase", context)

    def test_project_coordination_instructions_reach_hook_messages(self):
        config = {
            "warnInstruction": "Notify the operator and finish the current slice.",
            "blockInstruction": "Notify the operator and wait until reset.",
        }
        with tempfile.TemporaryDirectory() as directory:
            warn = self.run_hook(
                fixture=sample_payload(primary=80), config=config, state_dir=directory,
                now=1000, session="instruction-warn", event="SessionStart",
            )
            block = self.run_hook(
                fixture=sample_payload(primary=95), config=config, state_dir=directory,
                now=1000, session="instruction-block", event="PreToolUse",
            )
        self.assertIn("Notify the operator", json.loads(warn.stdout)["hookSpecificOutput"]["additionalContext"])
        self.assertIn("wait until reset", json.loads(block.stdout)["hookSpecificOutput"]["permissionDecisionReason"])

    def test_hook_reports_weekly_only_when_primary_window_is_unavailable(self):
        fixture = sample_payload(secondary=80)
        del fixture[0]["usage"]["primary"]
        del fixture[0]["pace"]["primary"]
        with tempfile.TemporaryDirectory() as directory:
            blocked = self.run_hook(
                fixture=fixture,
                config={},
                state_dir=directory,
                now=1000,
                session="weekly-only",
            )
        reason = json.loads(blocked.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("weekly=80%", reason)
        self.assertNotIn("primary=", reason)

    def test_block_keeps_prompt_turn_available_for_resume_coordination(self):
        with tempfile.TemporaryDirectory() as directory:
            session_start = self.run_hook(
                fixture=sample_payload(primary=95),
                config={},
                state_dir=directory,
                now=1000,
                session="session-start-block",
                event="SessionStart",
            )
            user_prompt = self.run_hook(
                fixture=sample_payload(primary=95),
                config={},
                state_dir=directory,
                now=1000,
                session="prompt-block",
                event="UserPromptSubmit",
            )
        for result in (session_start, user_prompt):
            output = json.loads(result.stdout)
            self.assertIn("additionalContext", output["hookSpecificOutput"])
            self.assertNotIn("decision", output)

    def test_block_allows_only_the_automation_update_tool_for_resume_coordination(self):
        with tempfile.TemporaryDirectory() as directory:
            automation = self.run_hook(
                fixture=sample_payload(primary=95),
                config={},
                state_dir=directory,
                now=1000,
                session="automation-update",
                tool_name="codex_app__automation_update",
            )
            arbitrary_mcp = self.run_hook(
                fixture=sample_payload(primary=95),
                config={},
                state_dir=directory,
                now=1000,
                session="arbitrary-mcp",
                tool_name="mcp__example__write",
            )
        self.assertEqual(automation.stdout, "")
        self.assertEqual(
            json.loads(arbitrary_mcp.stdout)["hookSpecificOutput"]["permissionDecision"],
            "deny",
        )

    def test_atomic_cache_writers_leave_valid_json(self):
        workers = 8
        barrier = threading.Barrier(workers)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            def write(index):
                barrier.wait()
                self.hook._write_cached(path, float(index), "fingerprint", {"decision": "block", "error": f"writer-{index}"})
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(write, index) for index in range(workers)]
                for future in futures:
                    future.result()
            state = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(state["result"]["decision"], "block")


if __name__ == "__main__":
    unittest.main()
