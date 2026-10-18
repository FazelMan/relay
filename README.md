# Relay

**Local-first, model-agnostic continuity for AI-assisted coding.**

Relay saves durable task state to ordinary project files so work can be resumed after a context limit, interrupted session, or switch between coding agents. It combines machine-readable checkpoints, a human/agent-readable `HANDOFF.md`, task identity, optional lifecycle hooks, and a resume reconciliation report.

> **Important:** Relay preserves task state; it does not recover hidden model reasoning or unsaved conversation. Its CLI `resume` command prepares and validates continuation information. The Skill's `/handoff resume` workflow is responsible for reading that information and continuing work in the current agent session. Relay does not automatically launch a different provider/session.

- No cloud database or MCP server required.
- Routine mechanical checkpointing does not call an LLM or provider API.
- Files remain in the workspace by default.
- Works with Claude Code, Cursor, Codex, and generic agents through host-specific instructions and CLI commands.

## Contents

- [Features and mental model](#features-and-mental-model)
- [Requirements](#requirements)
- [Installation](#installation)
- [First-run setup](#first-run-setup)
- [Daily workflow](#daily-workflow)
- [Skill commands: save, resume, status, plan](#skill-commands-save-resume-status-plan)
- [CLI reference](#cli-reference)
- [Task identity and routing](#task-identity-and-routing)
- [Checkpoints and semantic handoffs](#checkpoints-and-semantic-handoffs)
- [Handoff advice and preferences](#handoff-advice-and-preferences)
- [Guard, risk bands, and hooks](#guard-risk-bands-and-hooks)
- [Storage layout and history](#storage-layout-and-history)
- [Configuration reference](#configuration-reference)
- [Host compatibility](#host-compatibility)
- [Troubleshooting](#troubleshooting)
- [Security and safety](#security-and-safety)
- [Testing and development](#testing-and-development)
- [Documentation](#documentation)

## Features and mental model

| Component | Purpose |
|---|---|
| `checkpoint.json` | Versioned machine-readable state, Git/workspace observations, task metadata, and available monitoring signals |
| `HANDOFF.md` | Human-readable continuation guide: objective, current state, decisions, unfinished work, tests, blockers, next steps |
| `history/` | Bounded prior checkpoint snapshots |
| Active-task registry | Associates automatic hook events with the intended task |
| Mechanical checkpoint | Fast local snapshot; **no LLM call** |
| Semantic handoff | Agent-authored task meaning and next steps, merged with mechanical facts |
| Resume report | Validates checkpoint state and reports discrepancies plus a continuation instruction |
| Guard | Evaluates explicit context/quota signals, deduplicates warnings, and can checkpoint at risk points |
| Host adapters | Skill instructions and optional hook templates for supported coding environments |

### How the pieces fit together

1. The CLI records observable state such as the current Git branch, HEAD and working-tree summary.
2. The agent adds semantic information that cannot reliably be inferred from Git alone.
3. Relay stores both in task-specific files and retains bounded history.
4. On resume, the agent reads the saved files and checks them against the actual workspace.
5. The agent continues from the first genuinely unfinished step, preserving newer user changes.

## Requirements

- Python **3.9 or newer**.
- Git is recommended for branch, commit, and working-tree observations. Some features may be less informative without it.
- One supported coding agent if you want to use the Skill interface. The CLI itself can be run independently.
- No external API key is needed for mechanical checkpointing.

Check your Python version:

```bash
python3 --version
git --version
```

## Installation

Choose **one** of the following approaches.

### Option A — Clone Relay and use the CLI from source

```bash
git clone https://github.com/FazelMan/relay.git
cd relay
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
python3 -m relay --help
python3 -m relay status
```

The `PYTHONPATH` export applies to the current shell. Run it again in a new terminal, or set it in your shell configuration if desired. You can use the CLI without installing a host Skill.

### Option B — Install the Skill for your coding agent

Run these commands **from the Relay repository root**:

```bash
# Claude Code
./skills/handoff/scripts/install.sh claude-code

# Cursor
./skills/handoff/scripts/install.sh cursor

# Codex
./skills/handoff/scripts/install.sh codex
```

Default destinations:

| Host | Default destination |
|---|---|
| Claude Code | `~/.claude/skills/handoff` |
| Cursor | `~/.cursor/skills/handoff` |
| Codex | `~/.agents/skills/handoff` |

The installer copies Relay-owned files, backs up conflicting owned files, preserves unrelated custom files, writes `.relay-install-manifest.json`, and installs `bin/relay-run`. Re-running the installer is intended to be idempotent.

Install to a custom directory:

```bash
./skills/handoff/scripts/install.sh claude-code --dest "$HOME/.claude/skills/handoff"
python3 -m relay install cursor --dest ".cursor/skills/handoff"
```

Paths containing spaces are supported when quoted.

**After moving the Relay checkout**, re-run the installer so the installed wrapper's Relay root points at the correct location.

### Optional hooks

The installer does **not** silently modify host settings. To use lifecycle hooks:

1. Review the adapter's `hooks.json`.
2. Merge the relevant entries into the host's settings using that host's supported configuration process.
3. Review and trust the hooks according to your host's security model.
4. Set the active task before substantial work.
5. Verify hook behavior with a test task before relying on it.

For example, the installed Claude Code wrapper can be called as:

```bash
~/.claude/skills/handoff/bin/relay-run hook --host claude-code --event PreCompact
```

The `--with-hooks` installer option prints hook guidance; it does not automatically rewrite Claude Code or Codex settings.

### Uninstall

Uninstall removes only files recorded in Relay's install manifest. Custom files are preserved, and a destination without a Relay manifest is not treated as safe to delete.

```bash
# Uninstall the default installation for one host
./skills/handoff/scripts/install.sh uninstall
python3 -m relay uninstall --host claude-code

# Uninstall from an explicit directory
python3 -m relay uninstall --dest "$HOME/.claude/skills/handoff"
```

With no `--host` or `--dest`, the CLI checks the default install locations for Claude Code, Codex and Cursor.

## First-run setup

### 1. Choose a task ID

Use a short, stable slug for the piece of work, for example `billing-rate-limit` or `varzeshkar-program-templates-autopilot`.

### 2. Set the active task

```bash
python3 -m relay task set billing-rate-limit
python3 -m relay task get
```

This is especially important when hooks are enabled: automatic events need to know which task they belong to.

### 3. Create the first checkpoint and handoff

```bash
python3 -m relay checkpoint --task billing-rate-limit \
  --objective "Add rate limiting to the billing API" \
  --write-handoff
```

### 4. Inspect the saved state

```bash
python3 -m relay status --task billing-rate-limit
python3 -m relay resume --task billing-rate-limit
python3 -m relay handoff list
```

The `resume` CLI command prints a JSON report; it does not itself perform the coding work. In an installed Claude Code Skill, invoke `/handoff resume billing-rate-limit` to ask the agent to read, reconcile and continue the task.

## Daily workflow

### Before a long coding session

```bash
python3 -m relay task set my-feature
python3 -m relay status --task my-feature
```

### At a milestone or before switching sessions

In the agent, use `/handoff` to refresh the semantic handoff, or use the CLI:

```bash
python3 -m relay handoff --task my-feature
```

If the agent has prepared a semantic JSON patch, pass it explicitly:

```bash
python3 -m relay handoff --task my-feature --semantic-json /path/to/semantic-patch.json
```

The patch file must contain a JSON object. Include only information actually known, such as objective, decisions, next steps, blockers and tests that were actually run. Do not put secrets or the full conversation transcript into it.

### Resume work in the current agent

Claude Code:

```text
/handoff resume my-feature
```

Codex (where the installed Skill is available):

```text
$handoff resume my-feature
```

For other environments, follow their installed Skill/rule entrypoint or use the CLI to inspect the state:

```bash
python3 -m relay resume --task my-feature
```

A safe resume sequence is: read both artifacts → inspect current Git state → compare saved facts to the workspace → protect newer user edits → continue the first unfinished step → refresh the handoff after meaningful progress.

### When the task is complete

```bash
python3 -m relay handoff done my-feature
```

This marks the checkpoint task complete, removes its `HANDOFF.md`, and clears the active task if it matches. Checkpoint/history and project files are preserved.

### Discard a handoff without marking the task complete

```bash
python3 -m relay handoff delete my-feature --yes
```

Deletion requires `--yes`. It removes only `HANDOFF.md`; it does not mark the task complete or delete the checkpoint, history, or project files.

## Skill commands: save, resume, status, plan

The portable Skill defines four workflows:

| Invocation | Behavior |
|---|---|
| `/handoff` or `/handoff save [task-id]` | Refresh mechanical state and the semantic continuation guide |
| `/handoff resume [task-id]` | Read artifacts, reconcile against the workspace, and continue actual unfinished work in the current agent session |
| `/handoff status [task-id]` | Report checkpoint health, freshness, monitoring support and readiness |
| `/handoff plan [task-id]` | Create a continuation plan while keeping checkpoint facts separate |

If a task ID is omitted, the Skill should use the active task only when unambiguous. If multiple tasks are plausible, select one explicitly rather than guessing.

**Resume is not cross-provider auto-launch.** Relay does not start Claude/Codex/Cursor for you. Open the desired environment yourself, then use its Skill or the CLI.

## CLI reference

Run `python3 -m relay --help` and `python3 -m relay <command> --help` for the arguments supported by the installed version. The common commands are listed below.

### Global

```bash
python3 -m relay --version
python3 -m relay --help
```

### `checkpoint` — write a mechanical checkpoint

```bash
python3 -m relay checkpoint --task <task-id> [options]
```

| Option | Meaning |
|---|---|
| `--task <id>` | **Required.** Task identity |
| `--workspace <path>` | Project root; defaults to current directory |
| `--trigger <value>` | Trigger label stored in the checkpoint; defaults to `mechanical` |
| `--host <name>` | Optional host label |
| `--objective <text>` | Set the task objective |
| `--semantic-json <path>` | Merge a JSON object with semantic task information |
| `--write-handoff` | Also render `HANDOFF.md` |
| `--no-activate` | Do not set this task as active |

Example:

```bash
python3 -m relay checkpoint --task my-feature \
  --objective "Implement export endpoint" --write-handoff
```

Mechanical collection does not summarize the conversation, call an LLM, query provider APIs, or stage/commit/push Git changes.

### `handoff` — create, list, advise, complete or delete

Create or refresh:

```bash
python3 -m relay handoff --task <task-id> [--workspace <path>] \
  [--host <name>] [--objective <text>] [--semantic-json <path>] [--no-activate]
```

| Option | Meaning |
|---|---|
| `--task <id>` | Task to create/refresh |
| `--workspace <path>` | Project root |
| `--host <name>` | Optional host label |
| `--objective <text>` | Update objective |
| `--semantic-json <path>` | Merge semantic JSON patch |
| `--no-activate` | Do not change active task |

List handoffs:

```bash
python3 -m relay handoff list
```

Show evidence-based advice:

```bash
python3 -m relay handoff advise
python3 -m relay handoff advise my-feature
python3 -m relay handoff advise --task my-feature
```

Complete and remove the handoff document:

```bash
python3 -m relay handoff done my-feature
```

Delete only the handoff document (explicit confirmation required):

```bash
python3 -m relay handoff delete my-feature --yes
```

For `list`, `done`, `delete` and `advise`, a task ID may be provided as the positional argument; the parser also supports `--task` for these actions. The default no-action form requires `--task` to refresh a handoff.

### `resume` — reconcile saved state

```bash
python3 -m relay resume [--task <task-id>] [--workspace <path>]
```

Outputs JSON containing resume validity and, when available, the checkpoint/historical fallback selected, discrepancies, a `continuation_instruction`, and host hints. This command is read-only with respect to project work: it does not edit source files or execute the continuation instruction. The agent Skill must use this report as input and continue the work.

### `status` — inspect current state

```bash
python3 -m relay status [--task <task-id>] [--workspace <path>]
```

Reports Relay version, workspace, configured storage directory, active task, known tasks, legacy handoffs, Git state and monitoring capabilities. With a selected task it also reports checkpoint validity, timestamps, task status, risk, context/quota observations and cross-agent readiness.

### `task` — manage the active task

```bash
python3 -m relay task set <task-id> [--workspace <path>]
python3 -m relay task get [--workspace <path>]
python3 -m relay task clear [--workspace <path>]
```

- `set` writes the project-local active-task registry.
- `get` reports the active task and resolution.
- `clear` clears the registry.
- Creating a checkpoint or handoff normally activates its task unless `--no-activate` is passed.

### `guard-eval` — evaluate explicit risk signals

```bash
python3 -m relay guard-eval [--task <id>] [--context-pct <0-100>] \
  [--rate-limited] [--interrupted] [--resuming] [--source <label>] \
  [--host <name>] [--session-id <id>] [--no-dedupe] [--workspace <path>]
```

| Option | Meaning |
|---|---|
| `--task <id>` | Task identity; otherwise resolve active task/fallback |
| `--context-pct <number>` | Explicit context utilization percentage |
| `--rate-limited` | Record an explicit rate-limit/quota-critical signal |
| `--interrupted` | Mark an interrupted-session flow |
| `--resuming` | Mark a resume flow |
| `--source <label>` | Identify the metric source |
| `--host <name>` | Host label for generated checkpoint |
| `--session-id <id>` | Scope warning deduplication to a session |
| `--no-dedupe` | Do not suppress repeated warnings |
| `--workspace <path>` | Project root |

Examples:

```bash
python3 -m relay guard-eval --task my-feature --context-pct 65
python3 -m relay guard-eval --task my-feature --context-pct 95 --no-dedupe
python3 -m relay guard-eval --task my-feature --rate-limited
```

The parser also exposes `--handoff-ready`; current risk evaluation determines readiness from actual artifacts rather than trusting a user-provided readiness claim.

### `hook` — host lifecycle entrypoint

```bash
python3 -m relay hook --host <claude-code|codex|cursor|generic> \
  [--event <Event>] [--task <id>] [--session-id <id>] \
  [--force-checkpoint] [--workspace <path>]
```

Hook JSON is read from standard input. A malformed JSON event returns an error. Hook processing is mechanical and must not invoke an LLM. If `--task` is omitted, Relay uses active-task resolution. `--force-checkpoint` requests a checkpoint regardless of the event's normal trigger settings.

### `validate` — validate a checkpoint file

```bash
python3 -m relay validate plans/handoffs/my-feature/checkpoint.json
```

Returns JSON indicating whether schema validation passed and listing validation errors.

### `example-config` — print configuration template

```bash
python3 -m relay example-config
python3 -m relay example-config > relay.toml
```

Review the generated file before using it.

### `install` and `uninstall`

```bash
python3 -m relay install <claude-code|codex|cursor> [--dest <path>]
python3 -m relay uninstall [--host <claude-code|codex|cursor>] [--dest <path>]
```

See [Installation](#installation) for default destinations and safe-install behavior.

## Task identity and routing

Relay resolves task identity in this order:

1. Explicit `--task <id>`.
2. Environment variable `RELAY_TASK`.
3. Project registry `.relay/active-task.json` (set via `python3 -m relay task set <id>`).
4. Exactly one semantic task directory, when unambiguous.
5. Mechanical-only fallback: `unscoped-mechanical`.

The fallback is not a semantic task and must not absorb another task's meaning. Set the active task before substantial work so automatic checkpoints are associated with the correct task.

## Checkpoints and semantic handoffs

### Mechanical data

Mechanical checkpoints record observable information such as timestamps, checkpoint IDs and Git/workspace state. Existing semantic fields are retained where valid, but the mechanical process does not infer decisions or unfinished work from the conversation.

### Semantic JSON patches

For high-quality continuation, an agent should provide a small JSON object with fields supported by the checkpoint schema. Typical information includes:

- Task objective and current status.
- Decisions and constraints.
- Completed and unfinished work.
- Next steps and blockers.
- Tests actually run and their real results.
- Important files and relevant paths.

Use the schema and existing examples in [`skills/handoff/references/checkpoint-schema.md`](skills/handoff/references/checkpoint-schema.md) as the source of truth. Omit unknown information; never invent test results, commits or deployment verification.

### Resume safely

The resume process is a reconciliation, not a blind restore:

- Read the checkpoint and handoff.
- Inspect the actual branch, working tree, recent commits and relevant files.
- Identify discrepancies and newer changes.
- Preserve uncommitted user work.
- Continue from the first unfinished step.
- Re-run relevant validation when practical.
- Refresh the handoff after meaningful progress.

Relay never automatically resets or cleans the repository to match an older checkpoint.

## Handoff advice and preferences

Relay's default strategy is intended to balance cost efficiency with high-quality continuation. Configure it in the repository's `relay.toml`:

```toml
handoff_mode = "suggest"
handoff_optimize_for = "value"
handoff_detail = "standard"
```

### `handoff_mode`

- `manual`: strategy layer should not proactively recommend handoffs.
- `suggest`: provide a recommendation based on available checkpoint/workspace evidence.
- `prepare`: prefer preparing or refreshing handoff artifacts when evidence indicates it is useful.

### `handoff_optimize_for`

- `value`: cost-efficient continuation while retaining strong quality (default).
- `cost`: prioritize lower cost.
- `time`: prioritize speed.
- `quality`: prioritize completeness and quality.
- `balanced`: balance trade-offs.

These are preferences, not measured guarantees. Relay does not currently calculate actual provider spend or automatically switch models/agents based on these values.

### `handoff_detail`

- `compact`: reduce the generated handoff to selected safety-critical sections.
- `standard`: standard handoff detail.
- `full`: full handoff detail.

Run advice:

```bash
python3 -m relay handoff advise
python3 -m relay handoff advise my-feature
```

The output is JSON with recommendation, reasons, available evidence and cautions about missing signals. It does not call an LLM. Context utilization and quota are only used when reliable signals are available; no percentage, urgency, or savings claim is fabricated.

More configuration details: [docs/configuration.md](docs/configuration.md).

## Guard, risk bands, and hooks

Default context risk bands:

| Band | Threshold | Meaning |
|---|---:|---|
| Healthy | Below 65% | No context warning |
| Early | 65% | Early warning |
| Elevated | 80% | Higher risk |
| Critical | 90% | Critical risk |

Thresholds are configurable and boundaries are inclusive. Quota/rate-limit risk is evaluated separately: low context use does not imply quota is safe.

Warning deduplication is stored locally in `.relay/local/guard-state.json` and scoped by task and session. Repeated warnings of the same level can be suppressed during the cooldown; escalation to a more severe level should still be emitted.

Telemetry policy:

- Explicit `--context-pct` is accepted as supplied input.
- Claude Code `SessionStart.context_tokens` can be interpreted only when `context_capacity_tokens` is configured.
- A rate-limit flag can record a quota-critical signal.
- Transcript length is **never** converted into a fabricated context percentage.
- Unsupported telemetry remains unknown/unsupported.

For implementation details see [docs/handoff-guard.md](docs/handoff-guard.md) and [docs/auto-checkpoint.md](docs/auto-checkpoint.md).

## Storage layout and history

Default artifacts are stored under the project workspace:

```text
plans/handoffs/
  <task-id>/
    checkpoint.json
    HANDOFF.md
    history/
`.relay/
  active-task.json
  local/
    guard-state.json
```

- `checkpoint.json`: latest machine-readable state.
- `HANDOFF.md`: current continuation guide.
- `history/`: prior checkpoints retained up to `history_limit`.
- `.relay/active-task.json`: selected task for hooks and commands.
- `.relay/local/`: local warning-deduplication state; do not commit sensitive local data.

Legacy flat `plans/handoffs/HANDOFF_*.md` files may be listed for compatibility. New task handoffs use task directories.

## Configuration reference

Relay supports an optional `relay.toml`, `.relay.toml` or `relay.json` at the workspace root. Generate a starting TOML file:

```bash
python3 -m relay example-config > relay.toml
```

Review and edit it to suit the project.

| Setting | Default | Purpose |
|---|---|---|
| `storage_dir` | `plans/handoffs` | Artifact directory, relative to workspace by default |
| `history_limit` | `5` | Maximum retained checkpoint history per task |
| `warning_cooldown_seconds` | `300` | Warning deduplication cooldown |
| `thresholds.early` | `0.65` | Early context-risk threshold |
| `thresholds.elevated` | `0.80` | Elevated context-risk threshold |
| `thresholds.critical` | `0.90` | Critical context-risk threshold |
| `auto_handoff_on_critical` | `true` | Write a handoff on the critical guard path when applicable |
| `mechanical_on_precompact` | `true` | Enable mechanical checkpoint behavior for PreCompact |
| `mechanical_on_stop` | `false` | Enable mechanical checkpoint behavior for Stop |
| `context_capacity_tokens` | unset | Capacity needed to interpret Claude `context_tokens` |
| `handoff_mode` | `suggest` | `manual`, `suggest`, or `prepare` |
| `handoff_optimize_for` | `value` | `value`, `cost`, `time`, `quality`, or `balanced` |
| `handoff_detail` | `standard` | `compact`, `standard`, or `full` |
| `allow_paths_outside_workspace` | `false` | Security-sensitive opt-in for storage outside workspace |

Invalid threshold ordering is an error rather than silently ignored. Keep storage within the workspace unless you understand the implications of explicitly allowing external paths.

## Host compatibility

| Host | Entry point | Hooks / telemetry | Notes |
|---|---|---|---|
| Claude Code | `/handoff` | Optional PreCompact and SessionStart integration; context tokens only in supported events with configured capacity | Native Skill adapter |
| Cursor | Installed Skill/rule | No lifecycle hooks in this adapter; context/quota unsupported | Native Skill instructions |
| Codex | `$handoff` where supported by installed Skill | Optional hooks; trust may be required; telemetry unsupported unless supplied | Adapted integration |
| Other agents | CLI + portable instructions | Manual | Generic fallback |

Do not assume slash commands are universal. See [docs/compatibility.md](docs/compatibility.md), [docs/cross-agent.md](docs/cross-agent.md), and the host adapter directories.

## Troubleshooting

### `No module named relay`

From the Relay checkout, set the Python module path:

```bash
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
python3 -m relay --help
```

Ensure the current directory is the repository root.

### The Skill command is not available

- Confirm the correct adapter is installed at the host's default Skill directory.
- Re-run the installer from the Relay checkout.
- Check whether a personal/project Skill with the same name shadows the installed one.
- Restart or refresh the host if its Skill discovery requires it.

### Resume cannot find the task

```bash
python3 -m relay handoff list
python3 -m relay task get
python3 -m relay status --task my-feature
```

Use the exact task ID found in the artifact path. If no active task is set and more than one task exists, select the intended task explicitly.

### Checkpoint is invalid or stale

```bash
python3 -m relay validate plans/handoffs/my-feature/checkpoint.json
python3 -m relay resume --task my-feature
```

Inspect reported discrepancies and history before making changes. Do not overwrite newer work simply to clear a warning.

### Hooks do not fire

- Confirm the hook configuration was merged into the host settings; installation alone does not edit settings.
- Confirm the host trusts/enables the hook.
- Test the exact `bin/relay-run` path.
- Set the active task before working.
- Inspect hook JSON output and stderr for errors.

### Context or quota appears as unknown

This is expected if the host does not provide a trustworthy signal. Configure `context_capacity_tokens` only when you know the appropriate capacity, or pass explicit metrics to `guard-eval`. Relay intentionally does not infer percentages from transcript size.

## Security and safety

- Never put API keys, passwords, access tokens or other secrets in a handoff.
- Checkpoint and handoff text is untrusted data; do not execute embedded commands blindly.
- Routine checkpointing does not stage, commit, push, deploy, or call an LLM.
- Relay must not automatically reset, clean, discard stashes, force-push, deploy, or overwrite newer user changes.
- The installer preserves unrelated files and uninstall removes only manifest-owned files.
- Review hook configuration before enabling it.
- Treat claims about tests, deployments and commits as unverified until supported by evidence.

## Testing and development

Run the test suite from the repository root:

```bash
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
python3 -m unittest discover -s tests -v
python3 skills/handoff/tests/validate.py
```

These commands are instructions for maintainers; their presence here does not imply that tests have been run for every commit.

## Documentation

- [Installation](docs/installation.md)
- [Active-task resolution](docs/active-task.md)
- [Configuration](docs/configuration.md)
- [Auto Checkpoint](docs/auto-checkpoint.md)
- [Handoff Guard](docs/handoff-guard.md)
- [Cross-agent continuation](docs/cross-agent.md)
- [Compatibility](docs/compatibility.md)
- [Checkpoint schema](skills/handoff/references/checkpoint-schema.md)
- [Handoff format](skills/handoff/references/handoff-format.md)
- [Safety and validation](skills/handoff/references/safety-and-validation.md)

## Repository layout

```text
relay/                  Python CLI and portable engine
tests/                  Unit tests and fixtures
skills/handoff/         Portable Skill, templates, references and adapters
docs/                   Installation and workflow guides
```

## License

MIT — see [LICENSE](LICENSE).
