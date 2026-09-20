import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Deliberately separate from vite.config.ts rather than a `test` block
// merged into it: that file's tanstackStart() plugin does file-route
// generation and an SPA prerender pass, neither of which the test runner
// should be anywhere near. Vitest resolves `vitest.config.ts` in
// preference to `vite.config.ts` automatically, so nothing else needs to
// point at this file.
//
// Every current target under test is a pure function (search-params
// readers, the insights normaliser, largest-remainder rounding, pence
// parsing) -- no DOM is touched, so `environment: "node"` is enough and no
// jsdom/happy-dom dependency is pulled in. The `@/*` alias is resolved by
// hand rather than via `vite-tsconfig-paths` to keep that plugin (and the
// project-wide tsconfig scan it does) out of the test pipeline too.
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
