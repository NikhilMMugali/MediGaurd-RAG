import "@/lib/polyfills";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import App from "./App.tsx";
import { AuthProvider } from "@/auth/AuthContext";
import ErrorBoundary from "@/components/common/ErrorBoundary";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <ErrorBoundary
        fallback={(_error, reset) => (
          <div className="flex h-screen flex-col items-center justify-center gap-3 p-6 text-center text-sm">
            <p className="font-medium">Something went wrong displaying this page.</p>
            <p className="text-muted-foreground">Your data is safe. You can try again or reload.</p>
            <div className="flex gap-2">
              <button className="rounded-md border px-3 py-1.5" onClick={reset}>
                Try again
              </button>
              <button className="rounded-md border px-3 py-1.5" onClick={() => window.location.reload()}>
                Reload
              </button>
            </div>
          </div>
        )}
      >
        <AuthProvider>
          <App />
        </AuthProvider>
      </ErrorBoundary>
    </BrowserRouter>
  </StrictMode>,
);
