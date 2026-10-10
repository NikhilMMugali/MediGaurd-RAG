// pdf.js 6 calls Promise.withResolvers directly (Safari < 17.4 and older
// Chromium/Firefox lack it) on both the main thread and in its worker. Without
// this, opening a cited PDF threw and — with no error boundary — blanked the
// whole app. Imported first in main.tsx and in the worker wrapper.
//
// Cast rather than raising tsconfig's `lib` to ES2024: that would also let
// other ES2024 calls type-check without any runtime guarantee on old browsers.
const PromiseCtor = Promise as unknown as { withResolvers?: unknown };

if (typeof PromiseCtor.withResolvers !== "function") {
  PromiseCtor.withResolvers = function withResolvers<T>() {
    let resolve!: (value: T | PromiseLike<T>) => void;
    let reject!: (reason?: unknown) => void;
    const promise = new Promise<T>((res, rej) => {
      resolve = res;
      reject = rej;
    });
    return { promise, resolve, reject };
  };
}

export {};
