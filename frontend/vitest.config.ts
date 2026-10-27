import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

/**
 * Test-only config: mirrors tsconfig's `@/*` alias (Vitest doesn't read
 * tsconfig paths). Environments stay per-file (`node` default, `jsdom` pragma).
 * `vitest.setup.ts` stubs the browser APIs jsdom lacks (IntersectionObserver).
 */
export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    setupFiles: ["./vitest.setup.ts"],
  },
});
