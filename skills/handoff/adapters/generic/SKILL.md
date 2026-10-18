---
name: handoff
description: >
  Generic Relay handoff instructions for any coding agent that can read/write
  project files and run local commands. Use when the user asks to save or resume
  a task handoff without a host-specific adapter.
license: MIT
metadata:
  author: FazelMan/relay
  host: generic
  version: "0.2.0"
---

# Handoff — generic adapter

No slash commands are assumed. Follow the portable core and the Relay CLI.

## Minimum contract for a new host adapter

Expose whatever the host supports among:

1. **User entrypoints** — save / resume / status / plan
2. **Workspace access** — read/write under the project root
3. **Optional events** — pre-compaction, session start/end, stop
4. **Optional telemetry** — only documented host metrics (never fabricated %)

Map those into:

- `python3 -m relay checkpoint|handoff|status|resume|guard-eval|hook`

## Resume checklist

1. `python3 -m relay resume --task <id>`
2. Open `plans/handoffs/<id>/HANDOFF.md`
3. Diff recorded vs actual Git state
4. Continue first unfinished next step
5. Refresh handoff after milestones

## Limitations

- No automatic session launch or provider switching
- No context/quota monitoring unless the host supplies metrics to `guard-eval`
