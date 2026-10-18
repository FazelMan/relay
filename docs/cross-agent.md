# Cross-agent continuation

A receiving agent needs only the repository + portable artifacts. No original
model session, conversation, or proprietary IDs are required.

## Claude Code → Cursor

1. `python3 -m relay task set my-feature` (or `/handoff` which activates the task)
2. `/handoff` / `python3 -m relay handoff --task my-feature`
3. Open the **same repo** in Cursor (manual — no auto session launch)
4. `python3 -m relay resume --task my-feature`
5. Follow `continuation_instruction` in the JSON output / read `HANDOFF.md`
6. Verify Git; do not overwrite newer user changes
7. Continue next steps; refresh handoff after progress

## Claude Code → Codex

Same artifacts. In Codex: `$handoff resume my-feature` or the CLI.
Optional Codex hooks require `/hooks` trust.

## Resume output

`python3 -m relay resume` returns:

- Validated checkpoint path (or history fallback)
- Discrepancies / missing paths
- `continuation_instruction` (actionable Markdown)
- `host_hints` for Claude / Cursor / Codex / generic
- `overwrite_user_changes: false` (resume never writes the workspace)

## Fixtures

Unit fixtures under `tests/fixtures/cross_agent/` exercise Claude→Cursor and
Claude→Codex artifact layouts. They are **not** live host integration tests.
