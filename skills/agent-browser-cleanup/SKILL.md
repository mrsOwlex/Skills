---
name: agent-browser-cleanup
description: Enforce cleanup of local browser resources created through the agent-browser CLI. Use implicitly whenever an agent opens, navigates, or interacts with a website through Agent Browser, starts parallel agent-browser sessions, or finishes or aborts browser automation; close every session in the agent's namespace, verify that no agent-browser daemon remains, and never terminate the user's normal Chrome profile or unrelated Chromium/Electron processes.
---

# Agent Browser Cleanup

Treat every `agent-browser` invocation as owning browser resources that must be released before the task ends. Apply this skill automatically; do not wait for an explicit `$agent-browser-cleanup` request.

## Isolate agent sessions

Always use a unique namespace that belongs to the current agent:

```bash
export AGENT_BROWSER_NAMESPACE="agent-<worktree-or-task-id>"
SESSION="$(agent-browser session id --scope worktree --prefix <task>)"
agent-browser --session "$SESSION" open https://example.com
```

The cleanup helper operates on the current namespace and refuses a missing or shared `default` namespace. Do not run `close --all` in a namespace shared with another active agent. Never use `pkill`, `killall`, `kill -9`, AppleScript-wide Chrome termination, or deletion of a Chrome profile to clean up.

Namespace ownership is an explicit contract: the CLI cannot prove that two agents did not deliberately reuse the same non-default name. Include a fresh task/run identifier in every namespace and carry the exact value into the finalization command. A reused namespace is a cleanup blocker, not permission to close all sessions in it.

## Required finalization

Run the bundled helper as the final browser action, including after a failed or interrupted browser workflow:

```bash
CLEANUP="${CODEX_HOME:-$HOME/.codex}/skills/agent-browser-cleanup/scripts/cleanup_agent_browser.py"
python3 "$CLEANUP"
```

Resolve `CLEANUP` from the installed skill directory when the global skill is linked somewhere else. Do not assume the current project directory contains the skill.

The helper performs these checks in order:

1. Require a non-default `AGENT_BROWSER_NAMESPACE`.
2. Inspect each active session and require evidence that agent-browser launched its local browser; refuse unverified CDP or auto-connected sessions.
3. Run `agent-browser close --all --json` in the current namespace.
4. Poll `agent-browser session list --json` until the session list is empty.
5. Poll `agent-browser doctor --offline --quick --json` until the `daemon.active` check is `pass`.

Accept cleanup only when the helper exits with status `0` and prints JSON with `"ok": true`. The report includes the number of closed sessions and the namespace, but it does not delete saved authentication or restore-state files.

Each CLI invocation is bounded by a timeout. Verification failures and an asynchronously stopping daemon are retried only during the bounded polling window; a failed `close` command is an explicit blocker and is not blindly repeated. If cleanup fails, inspect the structured error on stderr, resolve the reported agent-browser problem, and run the helper again. Do not claim that the browser was cleaned up while verification is failing. Do not fall back to killing processes by name. If the CLI is unavailable or the daemon cannot be verified, report that as an explicit cleanup blocker.

For shell workflows that must clean up on every exit, preserve the original status while using the same helper from an `EXIT` trap:

```bash
cleanup() {
  original_status=$?
  python3 "$CLEANUP"
  cleanup_status=$?
  trap - EXIT
  if [ "$original_status" -ne 0 ]; then
    exit "$original_status"
  fi
  exit "$cleanup_status"
}
trap cleanup EXIT
```

Do not use this helper to close an existing personal Chrome connection created with `--cdp` or `--auto-connect` unless that connection was deliberately placed in an isolated agent namespace. The helper is for local agent-browser-launched sessions and their daemon.
