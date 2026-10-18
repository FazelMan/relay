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
  version: "0.2.1"
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
| `/handoff resume` [task] | Resume by reconciling files and continuing work in this session |
| `/handoff status` [task] | Status |
| `/handoff plan` [task] | Plan |

## Dashboard behavior

For `/handoff dashboard`, run `python3 -m relay dashboard` from the current project root. The CLI reuses an existing dashboard only when its reported workspace matches this project; otherwise it binds to the next available local port and opens the browser. Keep the server on `127.0.0.1` and do not suggest a global cross-project scan.

## Resume behavior

For `/handoff resume <task-id>`:

1. Run `python3 -m relay resume --task <task-id>` from the project root.
2. Read the task's `HANDOFF.md` and `checkpoint.json`.
3. Compare the saved state with current Git/workspace state and preserve newer user changes.
4. Continue the actual unfinished work. Do not merely return a copy-paste prompt or stop at a summary.
5. If no task ID is supplied, use the active task only when unambiguous; otherwise list available handoffs and ask which one.
6. Never reset/clean/stash-drop or overwrite changes to force the workspace to match the checkpoint. Ask before risky/destructive actions.
7. Report validation honestly and refresh the handoff after meaningful progress.

The skill continues work in the current Claude Code session. It does not claim to open another provider/session automatically.

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
