# `src/hooks/` — shared React hooks

Custom hooks used by more than one component (e.g. `useSession`, `useMediaQuery`).

Conventions:

- One hook per file: `useThing.ts` exporting `useThing`.
- Hooks NEVER call `fetch` directly — data hooks go through `@/lib/api`.
- No secrets, no tokens in hook state (sessions live in httpOnly cookies).

## Hooks

- `useAuth` (Stage 05) — `AuthProvider` access: `status`/`user` + actions. Throws
  outside the provider. Never exposes tokens (httpOnly cookies only).
- `useMediaQuery` (Stage 05) — reactive media-query match via
  `useSyncExternalStore` (SSR-safe: `false` until hydrated).
