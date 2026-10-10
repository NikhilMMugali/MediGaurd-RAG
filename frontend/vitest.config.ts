import path from "path";
import { fileURLToPath } from "url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Kept separate from vite.config.ts on purpose: vitest/config pulls in its
// own bundled copy of Vite's types, which can diverge in version from the
// project's top-level vite package used by `vite build` — importing
// defineConfig from "vitest/config" inside vite.config.ts made tsc -b (the
// production build's own type-check) fail with a Plugin-type mismatch.
// This file is outside every tsconfig's `include`, so tsc -b never sees it.
const dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
  },
});
