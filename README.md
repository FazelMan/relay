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

# Set / use an active task (hooks resolve this — never silent "default")
python3 -m relay task set my-feature

# Mechanical checkpoint (no LLM)
python3 -m relay checkpoint --task my-feature --objective "Add rate limiting" --write-handoff

# Status / resume prep (emits continuation_instruction for another agent)
python3 -m relay status --task my-feature
python3 -m relay resume --task my-feature

# Safe skill install (preserves custom files; installs bin/relay-run)
./skills/handoff/scripts/install.sh claude-code
./skills/handoff/scripts/install.sh cursor
./skills/handoff/scripts/install.sh codex
```

See [docs/active-task.md](docs/active-task.md), [docs/handoff-guard.md](docs/handoff-guard.md),
[docs/configuration.md](docs/configuration.md), and [docs/installation.md](docs/installation.md).

Artifacts land in:

```text
plans/handoffs/<task-id>/
  checkpoint.json
  HANDOFF.md
  history/              # retained checkpoint history
```

## Cross-agent example

1. Work in **Claude Code**; optional `PreCompact` hook saves a mechanical checkpoint.
2. Run `/handoff` (or `python3 -m relay handoff --task …`) before context/quota pressure peaks.
3. Inspect active handoffs with `python3 -m relay handoff list`; mark finished work with `python3 -m relay handoff done <task-id>`. This removes the handoff document from the list while preserving checkpoint/history. Use `python3 -m relay handoff delete <task-id> --yes` when discarding a handoff without marking the task complete.
4. Open the **same repository** in **Cursor** or **Codex**.
5. `python3 -m relay resume --task <id>` → read `HANDOFF.md` → verify Git → continue.
6. Refresh the checkpoint after milestones.

Details: [docs/cross-agent.md](docs/cross-agent.md).


## Handoff strategy and advice

Relay defaults to a **cost-efficient, high-quality** handoff strategy. Preferences live in your repository's `relay.toml` and persist until you edit them:

```toml
handoff_mode = "suggest"
handoff_optimize_for = "value"
handoff_detail = "standard"
```

Ask Relay for an evidence-based recommendation:

```bash
python3 -m relay handoff advise
python3 -m relay handoff advise my-feature
```

The command reports its recommendation, reasons, available evidence, and missing signals. It does not call an LLM, switch agents, claim guaranteed savings, or invent context/quota telemetry. See [docs/configuration.md](docs/configuration.md) for all options.

## Auto Checkpoint vs semantic handoff

| Kind | LLM? | When |
|------|------|------|
| Mechanical | **No** | Hooks, timers, explicit `relay checkpoint` / `relay hook` |
| Semantic | Agent may update fields | Milestones, decisions, user `/handoff` via `--semantic-json` |

Risk bands are distinct: **early (65%) / elevated (80%) / critical (90%)**.
Early warnings do not suppress later critical warnings.

See [docs/auto-checkpoint.md](docs/auto-checkpoint.md) and [docs/handoff-guard.md](docs/handoff-guard.md).

## Automatic vs manual

| Capability | Status |
|------------|--------|
| PreCompact mechanical save (hooks enabled + trusted) | Automatic |
| Active-task routing for hooks | Automatic **after** `relay task set` |
| Semantic handoff narrative | Manual / agent command |
| Context % / quota monitoring | Manual metrics or limited host signals |
| Opening another agent/session | **Manual** |

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
