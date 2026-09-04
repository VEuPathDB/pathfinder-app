import { useState } from "react";

/**
 * Extract a human-readable error message from an unknown thrown value.
 */
function toErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "string") return err;
  return String(err);
}

// ---------------------------------------------------------------------------
// Hook: useAsyncAction
// ---------------------------------------------------------------------------

interface AsyncActionState {
  /** Run an async function with automatic loading/error state management. */
  run: <T>(fn: () => Promise<T>) => Promise<T | undefined>;
  /** The last error message, or null if no error. */
  error: string | null;
  /** Whether a run is currently in progress. */
  loading: boolean;
  /** Clear the current error. */
  clearError: () => void;
}

/**
 * Shared async action hook that replaces repeated try/catch + setError patterns
 * across React components.
 *
 * @example
 * ```tsx
 * const { run, error, loading, clearError } = useAsyncAction();
 *
 * const handleClick = () => {
 *   run(async () => {
 *     const data = await fetchSomething();
 *     setSomeState(data);
 *   });
 * };
 * ```
 */
export function useAsyncAction(): AsyncActionState {
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const run = async <T>(fn: () => Promise<T>): Promise<T | undefined> => {
    setLoading(true);
    setError(null);
    try {
      const result = await fn();
      return result;
    } catch (err) {
      const msg = toErrorMessage(err);
      setError(msg);
      return undefined;
    } finally {
      setLoading(false);
    }
  };

  const clearError = () => setError(null);

  return { run, error, loading, clearError };
}
