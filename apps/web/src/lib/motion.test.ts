// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";

import { useEntrance, usePrefersReducedMotion } from "@/lib/motion";

interface MediaQueryState {
  matches: boolean;
  listeners: Set<() => void>;
}

function installMatchMedia(initialMatches: boolean): MediaQueryState {
  const state: MediaQueryState = { matches: initialMatches, listeners: new Set() };
  window.matchMedia = vi.fn().mockImplementation(() => ({
    get matches() {
      return state.matches;
    },
    media: "(prefers-reduced-motion: reduce)",
    onchange: null,
    addEventListener: (_event: "change", cb: () => void) => state.listeners.add(cb),
    removeEventListener: (_event: "change", cb: () => void) =>
      state.listeners.delete(cb),
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => true,
  })) as typeof window.matchMedia;
  return state;
}

const ENTRANCE = {
  initial: { opacity: 0, y: -4 },
  exit: { opacity: 0, y: -4 },
  transition: { duration: 0.15 },
};

afterEach(() => cleanup());

describe("usePrefersReducedMotion", () => {
  it("reports the media query state", () => {
    installMatchMedia(true);
    expect(renderHook(() => usePrefersReducedMotion()).result.current).toBe(true);
  });

  it("reports false when the viewer asked for no reduction", () => {
    installMatchMedia(false);
    expect(renderHook(() => usePrefersReducedMotion()).result.current).toBe(false);
  });

  it("follows a change to the preference", () => {
    const state = installMatchMedia(false);
    const { result } = renderHook(() => usePrefersReducedMotion());

    act(() => {
      state.matches = true;
      state.listeners.forEach((cb) => cb());
    });

    expect(result.current).toBe(true);
  });
});

describe("useEntrance", () => {
  it("passes the entrance through when motion is allowed", () => {
    installMatchMedia(false);
    const { result } = renderHook(() => useEntrance(ENTRANCE));
    expect(result.current).toBe(ENTRANCE);
  });

  it("renders settled and drops every duration under reduced motion", () => {
    installMatchMedia(true);
    const { result } = renderHook(() => useEntrance(ENTRANCE));
    expect(result.current).toEqual({
      initial: false,
      exit: { opacity: 0, y: -4 },
      transition: { duration: 0 },
    });
  });

  it("keeps an entrance that declares no exit", () => {
    installMatchMedia(true);
    const { result } = renderHook(() =>
      useEntrance({ initial: { opacity: 0 }, transition: { duration: 0.4, delay: 1 } }),
    );
    expect(result.current).toEqual({ initial: false, transition: { duration: 0 } });
  });

  it("settles an entrance the moment the preference turns on", () => {
    const state = installMatchMedia(false);
    const { result } = renderHook(() => useEntrance(ENTRANCE));
    expect(result.current.initial).toEqual({ opacity: 0, y: -4 });

    act(() => {
      state.matches = true;
      state.listeners.forEach((cb) => cb());
    });

    expect(result.current.initial).toBe(false);
  });
});
