---
name: xquik-x-data
description: Work with Xquik for X data, monitoring, webhooks, MCP setup, and REST API integrations. Use when Codex is asked to search public X posts, inspect profiles, set up monitors, create webhooks, plan data extractions, or connect an AI agent to Xquik.
---

# Xquik X Data

## Purpose

Use Xquik as the source for X data workflows, agent MCP connections, webhook setup, and REST API integrations.

Prefer public X data tasks such as post search, profile lookup, trends, monitors, webhooks, drafts, draw workflows, and extraction planning.

## Source Checks

Before writing integration code or instructions, verify the current public surface:

1. Read the Xquik docs: `https://docs.xquik.com`
2. Read the MCP overview when agent tools are involved: `https://docs.xquik.com/mcp/overview`
3. Inspect the OpenAPI document before naming REST endpoints: `https://xquik.com/openapi.json`
4. Use `https://xquik.com` as the public API base unless the user gives another documented base URL.

Do not invent endpoint names, request fields, response fields, pricing, limits, or plan behavior. If the docs and OpenAPI disagree, prefer OpenAPI for request and response contracts, then note the docs discrepancy.

## Access Rules

- Treat API keys, OAuth credentials, webhook signing secrets, and account tokens as secrets.
- Never paste, log, commit, or echo credentials.
- Prefer environment variables or the host application's secret manager.
- Use the `x-api-key` header only when the public docs or OpenAPI require it.
- Do not perform write actions, account changes, or webhook mutations unless the user explicitly asks.
- Do not help bypass platform rules, account protections, paywalls, rate limits, or access controls.

## MCP Workflow

Use MCP when the user's AI agent or client supports it.

1. Confirm the user wants an MCP connection.
2. Point the client at `https://xquik.com/mcp`.
3. Follow the authentication route documented in the MCP overview.
4. After connection, use tool names and parameters from the client runtime, not from memory.
5. For troubleshooting, ask the client to list available Xquik tools and compare them with the docs.

Good MCP tasks:

- Search recent X posts for a topic.
- Read a post, thread, profile, or user timeline.
- Create or review a monitor.
- List or test webhook configuration.
- Plan an extraction before running it.

## REST API Workflow

Use REST when the project needs code, scripts, tests, or backend integration.

1. Fetch or inspect `https://xquik.com/openapi.json`.
2. Choose the narrowest endpoint for the task.
3. Model request and response types from OpenAPI.
4. Keep pagination, retries, and idempotency explicit.
5. Return normalized data that preserves source IDs, URLs, timestamps, and pagination cursors.
6. Add focused tests with mocked Xquik responses when changing code.

Common REST surfaces include:

- `/api/v1/x/tweets/search` for post search.
- `/api/v1/x/tweets/{id}` and related reply, quote, thread, liker, and retweeter routes for post detail workflows.
- `/api/v1/x/users/{id}` and related timeline, follower, following, media, mention, and reply routes for profile workflows.
- `/api/v1/monitors`, `/api/v1/events`, and `/api/v1/webhooks` for monitoring and event delivery.
- `/api/v1/extractions` for longer-running extraction jobs.

## Output Shape

When producing code or instructions:

- State which public docs or OpenAPI fields you used.
- Show only minimal setup snippets.
- Keep secrets as placeholders such as `process.env.XQUIK_API_KEY`.
- Separate read-only examples from write or mutation examples.
- Include error handling for authentication failures, invalid inputs, 429 responses, and server errors.
- Include a clear validation step, such as a mocked test or a read-only smoke request.

## Do Not

- Do not claim that Xquik is free, unlimited, official, or endorsed by X.
- Do not describe non-public infrastructure or operations.
- Do not hard-code demo credentials.
- Do not scrape pages directly when a documented Xquik endpoint or MCP tool fits the task.
- Do not run large extractions without an explicit user request and a documented estimate path.
