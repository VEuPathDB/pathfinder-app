// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";
import { usePrefersReducedMotion } from "./usePrefersReducedMotion";

interface MockMediaQueryList {
  matches: boolean;
  listeners: Set<() => void>;
  addEventListener: (event: "change", cb: () => void) => void;
  removeEventListener: (event: "change", cb: () => void) => void;
}

function installMatchMedia(initialMatches: boolean): MockMediaQueryList {
  const state: MockMediaQueryList = {
    matches: initialMatches,
    listeners: new Set(),
    addEventListener(_event, cb) {
      state.listeners.add(cb);
    },
    removeEventListener(_event, cb) {
      state.listeners.delete(cb);
    },
  };
  window.matchMedia = vi.fn().mockImplementation(() => ({
    matches: state.matches,
    media: "(prefers-reduced-motion: reduce)",
    onchange: null,
    addEventListener: state.addEventListener,
    removeEventListener: state.removeEventListener,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => true,
  })) as typeof window.matchMedia;
  return state;
}

describe("usePrefersReducedMotion", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    // ensure clean
  });

  it("returns true when matchMedia matches", () => {
    installMatchMedia(true);
    const { result } = renderHook(() => usePrefersReducedMotion());
    expect(result.current).toBe(true);
  });

  it("returns false when matchMedia does not match", () => {
    installMatchMedia(false);
    const { result } = renderHook(() => usePrefersReducedMotion());
    expect(result.current).toBe(false);
  });

  it("updates on media-query change", () => {
    const state = installMatchMedia(false);
    const { result } = renderHook(() => usePrefersReducedMotion());
    expect(result.current).toBe(false);
    act(() => {
      state.matches = true;
      state.listeners.forEach((cb) => cb());
    });
    expect(result.current).toBe(true);
  });
});
