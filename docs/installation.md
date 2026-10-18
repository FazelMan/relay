# Installation

## Prerequisites

- Python 3.9+
- Git optional (file-only mode works; Git fields report unavailable)

```bash
cd /path/to/relay
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
python3 -m relay status
```

## Skill adapters

```bash
./skills/handoff/scripts/install.sh claude-code          # ~/.claude/skills/handoff
./skills/handoff/scripts/install.sh cursor               # ~/.cursor/skills/handoff
./skills/handoff/scripts/install.sh codex                # ~/.agents/skills/handoff
./skills/handoff/scripts/install.sh claude-code --with-hooks
./skills/handoff/scripts/install.sh uninstall
```

Project-local examples:

```bash
./skills/handoff/scripts/install.sh claude-code --dest .claude/skills/handoff
./skills/handoff/scripts/install.sh cursor --dest .cursor/skills/handoff
./skills/handoff/scripts/install.sh codex --dest .agents/skills/handoff
```

Install writes `RELAY_ROOT` and `relay-env.sh` so agents can set `PYTHONPATH`.

### Claude Code hooks

Merge `skills/handoff/adapters/claude-code/hooks.json` into your Claude Code hooks
configuration. Hooks are mechanical only. Review before enabling.

### Codex hooks

Copy `skills/handoff/adapters/codex/hooks.json` to `~/.codex/hooks.json` or
`<project>/.codex/hooks.json`, then trust via `/hooks`.

### Cursor rule (optional)

Copy `skills/handoff/adapters/cursor/relay-continuity.mdc` to `.cursor/rules/`.

## Uninstall

`./skills/handoff/scripts/install.sh uninstall` removes default personal skill
dirs. Project copies and host hook settings must be removed manually.

## Namespace conflicts

If `/handoff` already exists in Claude Code, rename the skill directory/frontmatter
or remove the other skill. Personal skills override project skills.

## Security notes

- No credentials in handoff files
- No automatic destructive Git
- Resume must verify the real workspace
