---
name: handoff
description: >
  Save, resume, or check Relay task handoffs for session continuity. Use when
  the user runs /handoff, /handoff resume, /handoff status, or /handoff plan.
argument-hint: "[save|resume|status|plan] [task-id]"
disable-model-invocation: true
license: MIT
metadata:
  author: FazelMan/relay
  host: claude-code
  version: "0.2.0"
---

# Handoff — Claude Code adapter

User-invoked (`disable-model-invocation: true`). Route `$ARGUMENTS`, then follow
portable core + Relay CLI.

## Capabilities (verified against Claude Code docs)

| Capability | Status |
|------------|--------|
| `/handoff` skill commands | Native |
| `PreCompact` hook → mechanical checkpoint | Supported (optional hooks.json) |
| `SessionStart` (compact/resume) hint | Supported |
| Continuous context utilization % | **Not** generally exposed; `context_tokens` on some SessionStart events only |
| Quota / billing telemetry | **Unsupported** here |
| Auto-launch another provider session | **Unsupported** — save artifacts and instruct the user |

## Argument routing

| Invocation | Mode |
|------------|------|
| `/handoff` or `/handoff save` [task] | Save |
| `/handoff resume` [task] | Resume |
| `/handoff status` [task] | Status |
| `/handoff plan` [task] | Plan |

## Load order

1. [PORTABLE.md](PORTABLE.md) (installed) or [../../SKILL.md](../../SKILL.md)
2. Ensure `PYTHONPATH` includes the Relay repo (or installed package) so
   `python3 -m relay` works.
3. Template/references as needed.

## Hooks

Optional: merge [hooks.json](hooks.json) into Claude Code settings. Hooks must
stay mechanical (no LLM). Trust/review per host policy.

## Namespace conflicts

Personal `~/.claude/skills/handoff` overrides project. Rename or remove
conflicts. See `docs/installation.md`.
