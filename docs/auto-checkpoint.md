# Auto Checkpoint

Routine checkpoint persistence **must not invoke an LLM**.

## Mechanical (zero-LLM)

`python3 -m relay checkpoint` and `python3 -m relay hook` record:

- Timestamps and checkpoint ids
- Git branch, HEAD, working-tree summary, changed paths (read-only)
- Prior semantic fields retained from the last checkpoint
- Optional context/quota observations **only when supplied** by the host or CLI

They do **not**:

- Summarize the conversation
- Call provider APIs
- Stage/commit/push
- Inject large diffs into the chat

## Semantic (agent-assisted)

At milestones, the agent writes a small JSON patch (objective, decisions,
next_steps, tests actually run) and passes `--semantic-json` to
`relay handoff` or `relay checkpoint`. Do not resend the full transcript.

## Scheduling

| Signal | Behavior |
|--------|----------|
| Claude/Codex `PreCompact` | Mechanical save (if hooks installed) |
| Explicit `/handoff` or CLI | Mechanical + semantic refresh |
| `guard-eval` critical | Mechanical save; optional HANDOFF.md |
| No events available | User/agent runs CLI periodically |

Prefer updating the current task checkpoint; history retention is bounded
(`history_limit` in config).

## Overhead

Mechanical writes are local filesystem JSON only. Keep semantic patches small.
Do not attach full checkpoint payloads to every model turn.
