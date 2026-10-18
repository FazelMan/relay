# Example: resume verification notes

Illustrative agent output for `/handoff resume` — not a claim that these checks were run in this repository.

## Verified

- Handoff path: `plans/handoffs/HANDOFF_add-rate-limiting_2026-03-18.md`
- Branch matches handoff: `feature/rate-limit`
- File exists: `src/middleware/rateLimit.ts`

## Discrepancies

- Handoff lists working tree dirty; current `git status` is clean — middleware may have been committed after the handoff was written. Re-read the file and recent commits before editing.

## Continuation

- First unfinished step still valid: confirm default limit, then wire middleware.
- Do not mark tests as passed; handoff correctly records them as not run.
