# Handoff Guard

Coordinates risk evaluation, warning dedupe, and when to checkpoint.

## Distinct risk bands

Context utilization maps to **separate** bands (defaults; configurable):

| Band | Default threshold | Meaning |
|------|-------------------|---------|
| healthy | &lt; 65% | No warning |
| early | ≥ 65% | Early warning |
| elevated | ≥ 80% | Elevated risk |
| critical | ≥ 90% | Critical risk |

Boundaries are inclusive of the higher band (65.0 → early, 80.0 → elevated, 90.0 → critical).

Combined `warning_level` is the worse of context vs quota. Low context utilization
**never** implies quota is safe.

User-facing `state` may be `handoff_ready` when artifacts exist and risk is
elevated/critical, or `interrupted` / `resuming` for those flows.

## Warning deduplication

Stored in `.relay/local/guard-state.json`, scoped by **task id + session id**.

- Same level within cooldown → suppressed
- **Escalation always emits** (early must not suppress critical)
- Return to healthy resets the escalation baseline

## Telemetry honesty

| Source | Accepted? |
|--------|-----------|
| `--context-pct` | Yes (`valid`) |
| Claude `SessionStart.context_tokens` + `context_capacity_tokens` | Yes |
| Transcript length / char counts | **Never** |
| Missing metrics | `unsupported` / `unknown` — no invented % |
| `--rate-limited` | Quota critical |

## CLI

```bash
python3 -m relay guard-eval --context-pct 65 --task my-feature --no-dedupe
python3 -m relay guard-eval --context-pct 95 --task my-feature
python3 -m relay guard-eval --rate-limited --task my-feature
```
