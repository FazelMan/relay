# Cross-agent continuation

## Claude Code → Cursor

1. In Claude Code: `/handoff my-feature` (or CLI `relay handoff --task my-feature`).
2. Confirm `plans/handoffs/my-feature/HANDOFF.md` and `checkpoint.json` exist.
3. Open the same repo in Cursor.
4. Ensure `PYTHONPATH` includes the Relay checkout (or install the skill).
5. Run `python3 -m relay resume --task my-feature`.
6. Read `HANDOFF.md`, verify Git, continue next steps.
7. After progress: `python3 -m relay handoff --task my-feature`.

Cursor does not receive Claude session IDs; only portable files matter.

## Claude Code → Codex

Same artifact paths. In Codex use `$handoff resume my-feature` or the CLI.
Optional Codex hooks need trust via `/hooks`.

## Generic agent

Point the agent at:

- `skills/handoff/SKILL.md` (or installed PORTABLE.md)
- `plans/handoffs/<task>/HANDOFF.md`
- `python3 -m relay resume --task <task>`

## If semantic handoff never ran

The last **mechanical** checkpoint remains. Resume reports what Git looked like;
ask the user to clarify intent for gaps.

## Corrupt latest checkpoint

Relay keeps history under `history/`. `resume` falls back to the newest valid
history entry and reports the failure.

## Another computer

Committed `plans/handoffs/` travels with Git. `.relay/local/` does **not**.
Machine-absolute paths in older checkpoints may need reinterpretation — always
reconcile against the local workspace.
