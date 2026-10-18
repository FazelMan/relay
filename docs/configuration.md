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
| `allow_paths_outside_workspace` | `false` | Security-sensitive; errors if mis-set with escaping `storage_dir` |

Invalid threshold ordering raises a hard error (not silently ignored).
