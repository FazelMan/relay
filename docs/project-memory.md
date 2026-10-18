# Project memory

Relay keeps task-specific decisions in `checkpoint.json`. For durable, project-wide conventions that should survive across tasks, you may keep a plain Markdown file named `PROJECT_MEMORY.md` at the workspace root.

Suggested structure:

```markdown
# Project Memory

## Architecture
- Current source of truth:
- Important boundaries:

## Decisions
- Decision — rationale — date/context.

## Constraints
- Rules the coding agent must preserve.

## Known pitfalls
- Failure patterns and verified fixes.
```

Keep this file concise and factual. Separate confirmed facts from assumptions, remove obsolete decisions, and never store credentials, tokens, personal data or other secrets. The dashboard can expose this file only to the local browser through its read-only API; it does not create or edit the file for you.

For task-specific decisions, next steps and test evidence, continue recording structured data in the existing checkpoint schema. Only record tests that were actually run and their real results.
