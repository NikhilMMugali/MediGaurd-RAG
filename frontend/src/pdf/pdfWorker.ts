// Thin wrapper so the polyfill is installed inside the worker's own global
// scope before pdf.js's worker code runs (a page-level polyfill doesn't reach
// a Web Worker). Import order is evaluation order.
import "@/lib/polyfills";
import "pdfjs-dist/legacy/build/pdf.worker.min.mjs";
