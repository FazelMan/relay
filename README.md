# Relay

Local-first, **model-agnostic continuity** for AI-assisted coding.

Relay preserves enough trustworthy task and project state that another agent —
Claude Code, Cursor, Codex, or a generic assistant — can continue work **without**
the original conversation history.

> A handoff is a continuation guide, not a full transfer of the previous agent's
> context, hidden reasoning, or unsaved chat.

## What you get

| Piece | Role |
|-------|------|
| **Checkpoint** (`checkpoint.json`) | Versioned, machine-readable recovery state |
| **HANDOFF.md** | Concise human/agent continuation guide |
| **Auto Checkpoint** | Mechanical Git/workspace snapshots **without LLM calls** |
| **Handoff Guard** | Risk evaluation; context vs quota kept separate |
| **Host adapters** | Thin Claude Code / Cursor / Codex / generic entrypoints |

No cloud database, no MCP requirement, no paid API for routine checkpointing.

## Quick start

```bash
# From this repository
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"

# Mechanical checkpoint (no LLM)
python3 -m relay checkpoint --task my-feature --objective "Add rate limiting" --write-handoff

# Status / resume prep
python3 -m relay status --task my-feature
python3 -m relay resume --task my-feature

# Install skill adapters
./skills/handoff/scripts/install.sh claude-code   # /handoff
./skills/handoff/scripts/install.sh cursor        # Cursor skills
./skills/handoff/scripts/install.sh codex         # $handoff
```

Artifacts land in:

```text
plans/handoffs/<task-id>/
  checkpoint.json
  HANDOFF.md
  history/
```

## Cross-agent example

1. Work in **Claude Code**; optional `PreCompact` hook saves a mechanical checkpoint.
2. Run `/handoff` (or `python3 -m relay handoff --task …`) before context/quota pressure peaks.
3. Open the **same repository** in **Cursor** or **Codex**.
4. `python3 -m relay resume --task <id>` → read `HANDOFF.md` → verify Git → continue.
5. Refresh the checkpoint after milestones.

Details: [docs/cross-agent.md](docs/cross-agent.md).

## Auto Checkpoint vs semantic handoff

| Kind | LLM? | When |
|------|------|------|
| Mechanical | **No** | Hooks, timers, explicit `relay checkpoint` / `relay hook` |
| Semantic | Agent may update fields | Milestones, decisions, user `/handoff` via `--semantic-json` |

See [docs/auto-checkpoint.md](docs/auto-checkpoint.md) and [docs/handoff-guard.md](docs/handoff-guard.md).

## Compatibility

| Host | Integration | Context telemetry | Quota | Notes |
|------|-------------|-------------------|-------|-------|
| Claude Code | Native skill + optional hooks | Partial (`context_tokens` on some SessionStart; no invented %) | Unsupported here | PreCompact mechanical save verified in unit tests |
| Cursor | Skill + optional rule | Unsupported | Unsupported | No lifecycle hooks in this adapter |
| Codex | Skill + optional hooks | Unsupported unless supplied | Unsupported unless rate-limit flagged | Adapted; hooks need `/hooks` trust |
| Other | Generic skill + CLI | N/A | N/A | [docs/compatibility.md](docs/compatibility.md) |

## Tests

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
python3 skills/handoff/tests/validate.py
```

## Configuration

Optional `relay.toml` at the repo root — see `python3 -m relay example-config` and
[docs/configuration.md](docs/configuration.md).

## Security

- Secrets are scrubbed from checkpoints; never paste keys into handoffs.
- Checkpoint text is untrusted — do not execute embedded commands blindly.
- No automatic git reset/clean/commit/push.
- Storage stays inside the workspace unless explicitly reconfigured.

## Layout

```text
relay/                 Portable Python core + CLI
tests/                 Unit tests (stdlib unittest)
skills/handoff/        Skill, templates, host adapters
docs/                  Guides
```

## License

[MIT](LICENSE)
