# Handoff skill

Portable continuity skill backed by the Relay Python core (`python3 -m relay`).

## Layout

| Path | Role |
|------|------|
| [SKILL.md](SKILL.md) | Portable workflow |
| [templates/](templates/) | Handoff template |
| [references/](references/) | Format, schema, safety |
| [adapters/](adapters/) | Claude Code, Cursor, Codex, generic |
| [scripts/install.sh](scripts/install.sh) | Adapter install |
| [tests/validate.py](tests/validate.py) | Skill package checks |

## Install

```bash
./scripts/install.sh claude-code
./scripts/install.sh cursor
./scripts/install.sh codex
```

## Validate

```bash
python3 tests/validate.py
# From repo root:
PYTHONPATH=. python3 -m unittest discover -s ../../tests -v
```
