# CLAUDE.md - Universal Agent Rules

- Keep this file minimal and stable; put project-specific details in `docs/`.
- Before changing code, check existing patterns and any available backups.
- Make one logical change at a time; avoid unrelated bundled edits.
- Never use type suppression (`as any`, `@ts-ignore`, `@ts-expect-error`).
- Never leave empty catches; handle or re-raise with clear context.
- Do not modify backup directories (`backup/`, `system/backup/`).
- After edits, run diagnostics, relevant tests, and build/typecheck when applicable.
- Do not claim completion without command evidence.
- If context is missing, search code/docs first; ask only as last resort.
- Keep debug code removable and clearly tagged.
- Prefer deterministic guardrails (linters/tests/checks) over prompt-only rules.
- Treat this file as a map; keep deep procedures in linked docs.
