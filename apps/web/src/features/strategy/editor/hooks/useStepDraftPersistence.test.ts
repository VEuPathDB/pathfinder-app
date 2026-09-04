// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import {
  stepDraftKey,
  useRecoveredDraft,
  useStepDraftPersistence,
} from "./useStepDraftPersistence";

beforeEach(() => {
  vi.useFakeTimers();
  window.localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
  window.localStorage.clear();
});

describe("stepDraftKey", () => {
  it("formats key as pathfinder.editor.draft.{strategyId}.{stepId}", () => {
    expect(stepDraftKey("strat-1", "step-7")).toBe(
      "pathfinder.editor.draft.strat-1.step-7",
    );
  });
});

describe("useStepDraftPersistence", () => {
  it("writes form values to localStorage after the throttle window", () => {
    const { result } = renderHook(() =>
      useStepDraftPersistence({ strategyId: "strat-1", stepId: "step-1" }),
    );
    act(() => {
      result.current.scheduleWrite({ organism: "Pf3D7" });
    });
    expect(window.localStorage.getItem(stepDraftKey("strat-1", "step-1"))).toEqual(
      null,
    );
    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(
      JSON.parse(window.localStorage.getItem(stepDraftKey("strat-1", "step-1"))!),
    ).toEqual({ organism: "Pf3D7" });
  });

  it("collapses multiple rapid writes into one localStorage write", () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    const { result } = renderHook(() =>
      useStepDraftPersistence({ strategyId: "strat-1", stepId: "step-1" }),
    );
    act(() => {
      result.current.scheduleWrite({ organism: "A" });
      result.current.scheduleWrite({ organism: "B" });
      result.current.scheduleWrite({ organism: "C" });
    });
    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(setItemSpy).toHaveBeenCalledTimes(1);
    expect(
      JSON.parse(window.localStorage.getItem(stepDraftKey("strat-1", "step-1"))!),
    ).toEqual({ organism: "C" });
  });

  it("loadDraft returns saved values", () => {
    window.localStorage.setItem(
      stepDraftKey("strat-1", "step-1"),
      JSON.stringify({ organism: "Pf3D7" }),
    );
    const { result } = renderHook(() =>
      useStepDraftPersistence({ strategyId: "strat-1", stepId: "step-1" }),
    );
    expect(result.current.loadDraft()).toEqual({ organism: "Pf3D7" });
  });

  it("clear removes the localStorage entry", () => {
    window.localStorage.setItem(
      stepDraftKey("strat-1", "step-1"),
      JSON.stringify({ organism: "Pf3D7" }),
    );
    const { result } = renderHook(() =>
      useStepDraftPersistence({ strategyId: "strat-1", stepId: "step-1" }),
    );
    act(() => {
      result.current.clear();
    });
    expect(window.localStorage.getItem(stepDraftKey("strat-1", "step-1"))).toEqual(
      null,
    );
  });

  it("flush writes immediately without waiting for throttle", () => {
    const { result } = renderHook(() =>
      useStepDraftPersistence({ strategyId: "strat-1", stepId: "step-1" }),
    );
    act(() => {
      result.current.scheduleWrite({ organism: "Pf3D7" });
      result.current.flush();
    });
    expect(
      JSON.parse(window.localStorage.getItem(stepDraftKey("strat-1", "step-1"))!),
    ).toEqual({ organism: "Pf3D7" });
  });

  it("uses unique key per (strategyId, stepId) pair", () => {
    const { result: r1 } = renderHook(() =>
      useStepDraftPersistence({ strategyId: "strat-1", stepId: "step-1" }),
    );
    const { result: r2 } = renderHook(() =>
      useStepDraftPersistence({ strategyId: "strat-1", stepId: "step-2" }),
    );
    act(() => {
      r1.current.scheduleWrite({ organism: "A" });
      r2.current.scheduleWrite({ organism: "B" });
    });
    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(
      JSON.parse(window.localStorage.getItem(stepDraftKey("strat-1", "step-1"))!),
    ).toEqual({ organism: "A" });
    expect(
      JSON.parse(window.localStorage.getItem(stepDraftKey("strat-1", "step-2"))!),
    ).toEqual({ organism: "B" });
  });
});

describe("useRecoveredDraft", () => {
  it("returns null when no draft is in storage", () => {
    const { result } = renderHook(() =>
      useRecoveredDraft({
        strategyId: "strat-1",
        stepId: "step-1",
        baselineValues: { organism: "Pf3D7" },
      }),
    );
    expect(result.current.draft).toEqual(null);
  });

  it("returns null when draft equals baseline", () => {
    window.localStorage.setItem(
      stepDraftKey("strat-1", "step-1"),
      JSON.stringify({ organism: "Pf3D7" }),
    );
    const { result } = renderHook(() =>
      useRecoveredDraft({
        strategyId: "strat-1",
        stepId: "step-1",
        baselineValues: { organism: "Pf3D7" },
      }),
    );
    expect(result.current.draft).toEqual(null);
  });

  it("returns the draft when it differs from baseline", () => {
    window.localStorage.setItem(
      stepDraftKey("strat-1", "step-1"),
      JSON.stringify({ organism: "PvP01" }),
    );
    const { result } = renderHook(() =>
      useRecoveredDraft({
        strategyId: "strat-1",
        stepId: "step-1",
        baselineValues: { organism: "Pf3D7" },
      }),
    );
    expect(result.current.draft).toEqual({ organism: "PvP01" });
  });

  it("dismiss clears storage and returns null thereafter", () => {
    window.localStorage.setItem(
      stepDraftKey("strat-1", "step-1"),
      JSON.stringify({ organism: "PvP01" }),
    );
    const { result } = renderHook(() =>
      useRecoveredDraft({
        strategyId: "strat-1",
        stepId: "step-1",
        baselineValues: { organism: "Pf3D7" },
      }),
    );
    act(() => {
      result.current.dismiss();
    });
    expect(result.current.draft).toEqual(null);
    expect(window.localStorage.getItem(stepDraftKey("strat-1", "step-1"))).toEqual(
      null,
    );
  });
});
