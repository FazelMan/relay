# Handoff Guard

Coordinates risk evaluation, warning dedupe, and when to checkpoint.

## Risk states

`healthy` → `elevated` → `critical` → `handoff_ready` | `interrupted` | `resuming`

Context risk and quota risk are tracked separately. Low context utilization
**never** implies quota is safe.

## Default thresholds (configurable)

| Band | Utilization |
|------|-------------|
| Early / elevated | ≥ 65% |
| Elevated | ≥ 80% |
| Critical | ≥ 90% |

## Telemetry honesty

| Source | What Relay accepts |
|--------|--------------------|
| Explicit `--context-pct` | Treated as `valid` for that evaluation |
| Claude `SessionStart.context_tokens` + configured `context_capacity_tokens` | Utilization derived only with both |
| Transcript character counts | **Rejected** — never used to invent % |
| Missing host metrics | `unsupported` / `unknown`; proactive mechanical checkpointing still OK |
| HTTP 429 / user-flagged `--rate-limited` | Quota `rate_limited` |

## Warnings

Deduplicated via `.relay/local/guard-state.json` (cooldown default 300s).

## CLI

```bash
python3 -m relay guard-eval --context-pct 82 --task my-feature
python3 -m relay guard-eval --rate-limited --task my-feature --no-dedupe
```
