# Configuration

Optional file at the repository root: `relay.toml` (or `.relay.toml` / `relay.json`).

```bash
python3 -m relay example-config > relay.toml
```

## Keys

| Key | Default | Meaning |
|-----|---------|---------|
| `storage_dir` | `plans/handoffs` | Relative to workspace |
| `history_limit` | `5` | Retained history files per task |
| `warning_cooldown_seconds` | `300` | Guard warning dedupe |
| `thresholds.early/elevated/critical` | 0.65 / 0.80 / 0.90 | Context bands |
| `auto_handoff_on_critical` | `true` | Write HANDOFF.md on critical guard path |
| `mechanical_on_precompact` | `true` | Hook behavior |
| `mechanical_on_stop` | `false` | Hook behavior |
| `context_capacity_tokens` | unset | Needed to interpret Claude `context_tokens` |
| `handoff_mode` | `suggest` | `manual`, `suggest`, or `prepare`; controls the preferred level of handoff assistance |
| `handoff_optimize_for` | `value` | `value` (cost-efficient with strong quality), `cost`, `time`, `quality`, or `balanced` |
| `handoff_detail` | `standard` | `compact`, `standard`, or `full` handoff detail |
| `allow_paths_outside_workspace` | `false` | Security-sensitive; errors if mis-set with escaping `storage_dir` |

Invalid threshold ordering raises a hard error (not silently ignored).


## Handoff strategy

The defaults favor **good value: avoid unnecessary work and cost while preserving high-quality continuation context**.

```toml
handoff_mode = "suggest"
handoff_optimize_for = "value"
handoff_detail = "standard"
```

- `manual`: do not proactively recommend handoff in the strategy layer.
- `suggest`: recommend a next step based on evidence available in checkpoints and workspace state.
- `prepare`: prefer preparing or refreshing handoff artifacts when the evidence indicates it is useful. This setting does not switch agents or run an LLM by itself.
- `value`: optimize for cost-efficient, high-quality continuation; this is a preference, not a promise of measured savings.
- `cost`, `time`, `quality`, `balanced`: prioritize that tradeoff.
- `compact`, `standard`, `full`: preferred handoff detail level.

Run `python3 -m relay handoff advise` (or add a task id: `python3 -m relay handoff advise my-task`) to get a JSON recommendation with reasons and known-data limitations.

**Preferences persist:** edit `relay.toml` in the repository. Relay reads these values on each invocation and does not rewrite this file, so your choices remain in place until you change them. Unsupported context/quota signals are never turned into invented percentages or guaranteed savings.
