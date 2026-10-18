# Active-task resolution

Hooks and automatic checkpoints must not dump unrelated work into a single
semantic task named `default`.

## Resolution order

1. Explicit `--task <id>`
2. Environment `RELAY_TASK`
3. Project registry `.relay/active-task.json` (`python3 -m relay task set <id>`)
4. Exactly one **semantic** task directory under `plans/handoffs/`
5. Safe fallback: `unscoped-mechanical` (mechanical snapshots only)

`unscoped-mechanical` is never registered as the active semantic task and never
silently absorbs another task's semantic fields.

## Commands

```bash
python3 -m relay task set my-feature
python3 -m relay task get
python3 -m relay task clear

# checkpoint/handoff also set the active task (unless --no-activate)
python3 -m relay checkpoint --task my-feature --write-handoff
```

## Hooks

Installed hooks call `bin/relay-run hook --host … --event …` **without**
`--task`. They resolve identity as above and report `task_resolution` in JSON.

Set the active task when starting meaningful work so PreCompact saves land on
the correct task.
