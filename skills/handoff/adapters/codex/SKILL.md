---
name: handoff
description: >
  Save, resume, or check Relay task handoffs for continuity. Use when the user
  says $handoff or asks to save/resume work across sessions or agents.
license: MIT
metadata:
  author: FazelMan/relay
  host: codex
  version: "0.2.0"
---

# Handoff — Codex adapter

Invoke with `$handoff` or `/skills`. Codex does **not** use Claude `/handoff`
slash commands as its skill API.

## Capabilities (verified against Codex docs)

| Capability | Status |
|------------|--------|
| Skills in `~/.agents/skills` / `.agents/skills` | Native |
| Lifecycle hooks (`PreCompact`, `SessionStart`, …) | Supported via `hooks.json` (requires `/hooks` trust) |
| Continuous context % | **Not claimed** — treat as unsupported unless you pass metrics to `guard-eval` |
| Quota telemetry | **Unsupported** unless an explicit rate-limit signal is supplied |
| Runtime E2E of this adapter | **Adapted** — conventions verified; live Codex session not required for unit tests |

## Modes

Parse save / resume / status / plan from the user message; run matching
`python3 -m relay …` flows from the portable core.

## Hooks

Optional project or user [hooks.json](hooks.json). Non-managed hooks need trust
review in Codex (`/hooks`).

## Install

```bash
./skills/handoff/scripts/install.sh codex
```
