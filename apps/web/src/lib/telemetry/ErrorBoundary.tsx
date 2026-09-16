"use client";

/**
 * Top-level React error boundary.
 *
 * Catches render-phase + lifecycle errors anywhere in the app tree and
 * forwards them to `logError` with source `react.errorBoundary`. Renders a
 * minimal fallback UI with a reload button - we don't try to recover
 * partial state because a thrown render error usually leaves the component
 * tree in an unknown state.
 *
 * We keep this as a class component because that's still the only way to
 * subscribe to React's `componentDidCatch` - there is no hook equivalent.
 */

import { Component, type ErrorInfo, type ReactNode } from "react";

import { logError } from "./logError";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  errorMessage: string | null;
}

export class TelemetryErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, errorMessage: null };
  }

  static getDerivedStateFromError(error: unknown): State {
    return {
      hasError: true,
      errorMessage: error instanceof Error ? error.message : String(error),
    };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    const base = {
      source: "react.errorBoundary" as const,
      extra: {
        "react.component_stack": (info.componentStack ?? "").slice(0, 2000),
      },
    };
    if (typeof window !== "undefined") {
      logError(error, { ...base, route: window.location.pathname });
    } else {
      logError(error, base);
    }
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div
          role="alert"
          className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center"
        >
          <h2 className="text-lg font-semibold">Something went wrong.</h2>
          <p className="max-w-md text-sm text-muted-foreground">
            {this.state.errorMessage ?? "An unexpected error occurred."}
          </p>
          <button
            type="button"
            className="rounded bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground"
            onClick={() => {
              window.location.reload();
            }}
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
