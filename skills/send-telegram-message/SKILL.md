---
name: send-telegram-message
description: Send a user-supplied message through a Telegram bot using standalone user-level credentials. Use when the user explicitly invokes this skill or asks Codex to send, deliver, notify, or message them via Telegram using TELEGRAM_BOT_TOKEN and OWNER_CHAT_ID from the environment or the private Codex Telegram credential file.
---

# Send Telegram Message

Send one exact user-approved plaintext message through the Telegram Bot API with the bundled dependency-free Node.js script.

## Workflow

1. Resolve the message text. Preserve wording and line breaks unless the user asks for editing. Treat an explicit request to send a concrete message as authorization to perform the external action. Ask for the missing text only when no concrete message can be inferred.
2. Resolve `scripts/send-telegram-message.mjs` from this installed skill directory to an absolute path.
3. Require Node.js 18 or newer. Do not install a Telegram SDK or add dependencies.
4. Load only these credentials:
   - `TELEGRAM_BOT_TOKEN`
   - `OWNER_CHAT_ID`
5. Prefer already-exported credentials. Otherwise let the script load `${XDG_CONFIG_HOME:-$HOME/.config}/codex/send-telegram-message.env`. Respect `TELEGRAM_SKILL_ENV_FILE` as an explicit file override. Do not search workspaces or project folders.
6. Pipe the message through stdin. Never place the bot token, chat ID, or message in command-line arguments. Use a single-quoted heredoc delimiter so shell syntax in the message is not evaluated.
7. Inspect the script's JSON result. Report success only for `telegram_message_sent`. On `telegram_message_failed`, report the error, `sentChunks`/`totalChunks`, and `deliveryUnknown`. Never retry a failed attempted delivery without fresh explicit user approval: Telegram may have accepted the current chunk before a timeout or network failure became visible, even when `sentChunks` is zero.

## Commands

With credentials already exported:

```bash
SENDER="/absolute/path/to/send-telegram-message/scripts/send-telegram-message.mjs"
node "$SENDER" <<'CODEX_TELEGRAM_MESSAGE'
Exact message text
CODEX_TELEGRAM_MESSAGE
```

The same command automatically uses the private user-level credential file when credentials are not exported:

```bash
SENDER="/absolute/path/to/send-telegram-message/scripts/send-telegram-message.mjs"
node "$SENDER" <<'CODEX_TELEGRAM_MESSAGE'
Exact message text
CODEX_TELEGRAM_MESSAGE
```

Choose a different quoted heredoc delimiter if the message contains a line exactly equal to `CODEX_TELEGRAM_MESSAGE`.

The CLI removes exactly one final `LF` or `CRLF` added by the heredoc framing. To intentionally end the Telegram message with a newline, put one additional blank line before the delimiter.

## Credential Setup

Resolve `scripts/configure-telegram-env.mjs` from this installed skill directory. With `TELEGRAM_BOT_TOKEN` and `OWNER_CHAT_ID` already present in the current process environment, run it once:

```bash
CONFIGURATOR="/absolute/path/to/send-telegram-message/scripts/configure-telegram-env.mjs"
node "$CONFIGURATOR"
```

Write credentials to `${XDG_CONFIG_HOME:-$HOME/.config}/codex/send-telegram-message.env` with mode `0600`. Use `TELEGRAM_SKILL_ENV_FILE` only when an explicit alternate location is required. Never print credential values.

## Safety and Output

- Never display, log, copy, or commit credential values.
- Refuse credential symlinks and files readable by group or others; use a regular file with mode `0600`.
- Never read project modules or workspace configuration; use only exported values or the standalone user credential file.
- Send plaintext without Telegram parse mode so user content cannot accidentally become active Telegram HTML.
- Split messages at paragraph or line boundaries into chunks of at most 4000 UTF-16 code units while preserving all content and keeping Unicode surrogate pairs intact.
- Send chunks sequentially without automatic retry.
- Emit structured JSON without the token, chat ID, or message body.
