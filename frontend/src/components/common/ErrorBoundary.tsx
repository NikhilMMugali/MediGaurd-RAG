import * as React from "react";

interface ErrorBoundaryProps {
  children: React.ReactNode;
  // Rendered instead of the children after a render error. Receives a reset
  // callback so the user can retry without reloading the whole app.
  fallback: (error: Error, reset: () => void) => React.ReactNode;
  // When this value changes the boundary clears its error — e.g. a different
  // citation was selected, so the previous failure no longer applies.
  resetKey?: string | number | null;
  onError?: (error: Error) => void;
}

interface ErrorBoundaryState {
  error: Error | null;
  resetKey: string | number | null | undefined;
}

// Without a boundary, any error thrown while rendering (react-pdf throws on
// an unparseable PDF; pdf.js throws on browsers missing newer APIs)
// unmounts the entire React tree and leaves a blank white page.
export default class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null, resetKey: this.props.resetKey };

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { error };
  }

  // Clears a previous failure when resetKey changes (e.g. another citation
  // was selected), so one bad document doesn't keep showing its error.
  static getDerivedStateFromProps(props: ErrorBoundaryProps, state: ErrorBoundaryState): Partial<ErrorBoundaryState> | null {
    return props.resetKey !== state.resetKey ? { error: null, resetKey: props.resetKey } : null;
  }

  componentDidCatch(error: Error) {
    console.error("ErrorBoundary caught:", error);
    this.props.onError?.(error);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) return this.props.fallback(this.state.error, this.reset);
    return this.props.children;
  }
}
