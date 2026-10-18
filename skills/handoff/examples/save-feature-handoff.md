# Handoff: Add rate limiting to public API

> **Status:** in_progress  
> **Updated:** 2026-03-18  
> **Path:** `plans/handoffs/HANDOFF_add-rate-limiting_2026-03-18.md`

## Goal and scope

- **Goal:** Add per-IP rate limiting to public HTTP API routes.
- **In scope:** Middleware, config defaults, unit tests for the limiter.
- **Out of scope:** Redis-backed distributed limits; UI changes.

## User requirements and constraints

- Must not require Redis for the first version (in-memory is OK).
- Preserve existing response shapes on success; on limit use HTTP 429.
- Do not commit or push unless asked.

## Status summary

In-memory middleware is sketched in `src/middleware/rateLimit.ts` but not wired into the app router. Tests are not run yet.

## Decisions (confirmed)

| Decision | Rationale | Evidence (path / commit) |
|----------|-----------|--------------------------|
| In-memory store for v1 | User constraint: no Redis yet | user-stated |
| 429 + `Retry-After` | Common API convention | observed prior routes in `src/http/errors.ts` |

## Findings

- App mounts middleware in `src/app.ts` via `app.use(...)`.
- Existing error helper supports status codes; 429 not used yet.

## Failed approaches

| Approach | Why it failed |
|----------|---------------|
| Sliding window with per-request heap | Overkill for v1; user asked for simplest working limit |

## Files changed

| Path | Purpose |
|------|---------|
| `src/middleware/rateLimit.ts` | New in-memory limiter (draft) |

## Repository state

- **Branch:** `feature/rate-limit`
- **Relevant commits:** none yet for this work (uncommitted)
- **Working tree:** dirty — `src/middleware/rateLimit.ts` untracked
- **Git available:** yes

## Tests and checks

| Check | Ran? | Result |
|-------|------|--------|
| Unit tests for limiter | no | not run |
| Full test suite | no | not run |
| Typecheck | no | not run |

## Blockers and risks

- In-memory store will not coordinate across multiple processes (accepted for v1).

## Open questions

- Default: 100 requests / minute / IP — confirm before wiring.

## Next steps (ordered)

1. Confirm default limit with user (100/min/IP).
2. Wire middleware in `src/app.ts` for public routes only.
3. Add unit tests under `src/middleware/rateLimit.test.ts`.
4. Run unit tests and typecheck; record results in this handoff.

## Resume instructions

For a fresh agent:

1. Read this file.
2. Verify against current Git status and the paths above.
3. Start at the first unfinished next step.
4. Do not trust claims marked unverified.

## References

- Project docs: `README.md` (API overview)
- Related handoffs: none

## Provenance notes

- **Observed:** middleware mount pattern in `src/app.ts`; dirty working tree
- **User-stated:** no Redis; no commit unless asked
- **Unverified assumptions:** 100/min/IP default (needs confirmation)
