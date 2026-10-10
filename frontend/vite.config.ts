import path from "path";
import { fileURLToPath } from "url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [
      { find: "@", replacement: path.resolve(dirname, "./src") },
      // react-pdf imports the standard pdf.js build, which needs very recent
      // browser APIs (Promise.withResolvers, ...) and throws on older
      // Safari/Chromium. The legacy build bundles polyfills for them.
      { find: /^pdfjs-dist$/, replacement: path.resolve(dirname, "node_modules/pdfjs-dist/legacy/build/pdf.mjs") },
      { find: /^pdfjs-dist\/web\/pdf_viewer\.mjs$/, replacement: path.resolve(dirname, "node_modules/pdfjs-dist/legacy/web/pdf_viewer.mjs") },
    ],
  },
  worker: { format: "es" },
  server: {
    port: 5173,
  },
});
