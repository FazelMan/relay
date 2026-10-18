# Handoff format reference

## Canonical layout (preferred)

```text
plans/handoffs/<task-id>/
  checkpoint.json
  HANDOFF.md
  history/checkpoint-*.json
```

Generate `HANDOFF.md` with `python3 -m relay handoff --task <task-id>` (or the
skill save workflow). Prefer the generator over hand-editing structure.

## Legacy flat files

Older installs may use `plans/handoffs/HANDOFF_<slug>_<date>.md`. Still
discoverable via `relay status` (`legacy_handoffs`). Migrate by creating a task
directory and running `relay handoff`.

## Required HANDOFF.md sections

Match the generator / [templates/HANDOFF.md](../templates/HANDOFF.md):

1. Task objective
2. Current status
3. Completed
4. Unfinished
5. Decisions
6. Files and changes
7. Tests and results
8. Blockers and risks
9. Next recommended action
10. Validate workspace before editing

## Index (optional)

`plans/handoffs/INDEX.md` may link task folders. Do not duplicate bodies.
