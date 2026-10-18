# Compatibility

| Level | Meaning |
|-------|---------|
| **Native** | Documented host format + install path |
| **Adapted** | Conventions verified; limited or untested runtime |
| **Generic** | CLI + Markdown only |

## Handoff / Relay

| Host | Level | Entry | Hooks | Context | Quota |
|------|-------|-------|-------|---------|-------|
| Claude Code | Native | `/handoff` | Optional PreCompact / SessionStart | Partial | Unsupported |
| Cursor | Native skill | Skill / agent instruction | None in this repo | Unsupported | Unsupported |
| Codex | Adapted | `$handoff` | Optional (trust required) | Unsupported unless supplied | Unsupported unless flagged |
| Other | Generic | Manual / PORTABLE.md | N/A | N/A | N/A |

Do not assume slash commands are universal.

## Adapter contract

A new adapter should provide only what the host actually supports:

1. User entrypoints (save/resume/status/plan)
2. Workspace file access
3. Optional lifecycle events wired to `python3 -m relay hook`
4. Optional telemetry passed to `guard-eval` — never fabricated

## Adding an adapter

1. Keep `relay/` as the portable engine.
2. Add `skills/handoff/adapters/<host>/`.
3. Document capability rows honestly.
4. Extend `scripts/install.sh` when paths are stable.
5. Add tests with fixtures/mocks — no live paid API.
