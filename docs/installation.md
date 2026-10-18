# Installation

## Prerequisites

- Python 3.9+
- Git optional

```bash
cd /path/to/relay
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
python3 -m relay status
```

## Safe skill install

Install is **non-destructive**:

- Copies only Relay-owned files
- Backs up conflicting files to `.relay-backup-<timestamp>/`
- Preserves unrelated custom files in the destination
- Writes `.relay-install-manifest.json`
- Installs `bin/relay-run` (sets `PYTHONPATH` from `RELAY_ROOT`)
- Idempotent on re-run

Default destinations:

- Claude Code: `~/.claude/skills/handoff`
- Cursor: `~/.cursor/skills/handoff`
- Codex: `~/.agents/skills/handoff`

```bash
./skills/handoff/scripts/install.sh claude-code
./skills/handoff/scripts/install.sh cursor
./skills/handoff/scripts/install.sh codex --with-hooks

# or
python3 -m relay install claude-code
python3 -m relay install cursor --dest ".cursor/skills/handoff"
```

Paths with spaces are supported (`--dest "/tmp/my skills/handoff"`).

### Uninstall

Removes **only** files listed in the install manifest. Custom files remain.
Refuses to delete a directory that has no Relay manifest.

```bash
./skills/handoff/scripts/install.sh uninstall
python3 -m relay uninstall --host claude-code
python3 -m relay uninstall --dest ~/.claude/skills/handoff
```

## Hooks and package location

Do **not** rely on a global undocumented `PYTHONPATH`. After install, hooks
should invoke:

```text
~/.claude/skills/handoff/bin/relay-run hook --host claude-code --event PreCompact
```

`relay-run` reads sibling `RELAY_ROOT` (absolute path to the Relay checkout
written at install time). Re-run install after moving the Relay repo.

Merge `hooks.json` from the adapter into host settings manually; install does
not silently rewrite Claude/Codex settings.

Omit `--task` in hooks; use the [active-task registry](active-task.md).

## What is automatic vs manual

| Action | Automatic? |
|--------|------------|
| Mechanical checkpoint on PreCompact (if hooks trusted/enabled) | Yes |
| Semantic HANDOFF.md content | Manual / agent `/handoff` |
| Context % monitoring | Only with explicit metrics or configured capacity |
| Quota monitoring | Only with explicit rate-limit signal |
| Opening Cursor/Codex sessions | **Manual** |

## Security notes

- No credentials in handoff files
- No automatic destructive Git
- Resume verifies the real workspace
- Uninstall never deletes arbitrary project trees without a manifest
