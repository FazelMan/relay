# Checkpoint schema (1.0.0)

Machine-readable recovery state: `plans/handoffs/<task-id>/checkpoint.json`.

## Top-level fields

| Field | Purpose |
|-------|---------|
| `schema_version` | `1.0.0` |
| `checkpoint_id` | Unique id per write |
| `task_id` | Stable task slug |
| `updated_at` | ISO-8601 UTC |
| `task` | Objective, status, decisions, files, tests, next_steps |
| `repository` | Branch, HEAD, working tree, changed paths |
| `context` | Utilization metrics + reliability |
| `quota` | Quota/rate-limit observation + reliability |
| `risk` | Guard state (`healthy`…`resuming`) |
| `provenance` | `mechanical` / `semantic` / `handoff` + host |
| `integrity` | Validation metadata |

Unknown values must be `null`, empty lists, or reliability `unsupported` /
`unknown`. Do not invent filler.

## Reliability enum

`valid` | `stale` | `historical` | `rate_limited` | `unavailable` | `unsupported` | `unknown`

## Validation

```bash
python3 -m relay validate plans/handoffs/<task-id>/checkpoint.json
```
