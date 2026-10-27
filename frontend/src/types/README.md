# `src/types/` — shared TypeScript types

Cross-cutting domain types mirrored from `the project contract` (e.g. `analysis.ts`,
`issue.ts`, `user.ts`). Colocated component prop types stay next to their components.

Conventions:

- Types mirror the API contract exactly (same names, same optionality).
- Prefer `interface` for objects, union literals for enums (`"low" | "medium" | …`).
- No `any` without a justification comment (typed per `tsconfig` strict).
- First types land with the features that need them — this folder starts empty.
