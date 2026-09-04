/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

import { useStrategyHistory } from "./useStrategySelectors";

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client }, children);
  }
  return Wrapper;
}

describe("state/useStrategySelectors", () => {
  it("useStrategyHistory returns undo/redo functions and pushSnapshot", () => {
    const { result } = renderHook(() => useStrategyHistory("strategy-1"), {
      wrapper: makeWrapper(),
    });
    expect(typeof result.current.undo).toBe("function");
    expect(typeof result.current.redo).toBe("function");
    expect(typeof result.current.canUndo).toBe("function");
    expect(typeof result.current.canRedo).toBe("function");
    expect(typeof result.current.pushSnapshot).toBe("function");
  });
});
