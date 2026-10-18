# Contributing

Relay is a **portable continuity engine** (`relay/`) plus thin **host adapters**
under `skills/handoff/adapters/`.

## Principles

1. Mechanical checkpointing never calls an LLM.
2. Do not fabricate context/quota percentages.
3. Prefer extending `relay/` over duplicating logic in adapters.
4. Document support levels honestly (native / adapted / generic).
5. No MCP or cloud dependency for core features.
6. Tests use stdlib `unittest` — no paid APIs.

## Adding a host adapter

1. Verify current host docs (skills, hooks, telemetry).
2. Add `skills/handoff/adapters/<host>/` with capability table.
3. Wire events to `python3 -m relay hook` only when supported.
4. Update `scripts/install.sh`, `docs/compatibility.md`, and tests.

## License

Contributions are MIT ([LICENSE](LICENSE)).
