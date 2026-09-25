/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useMemoryFocusStore } from "@/state/useMemoryFocusStore";
import { useModalState } from "./useModalState";

afterEach(() => {
  act(() => useMemoryFocusStore.getState().clearFocus());
});

describe("useModalState", () => {
  it("starts with all modals closed", () => {
    const { result } = renderHook(() => useModalState());
    expect(result.current.showSettings).toBe(false);
    expect(result.current.graphEditing).toBe(false);
  });

  describe("settings modal", () => {
    it("opens and closes", () => {
      const { result } = renderHook(() => useModalState());
      act(() => result.current.openSettings());
      expect(result.current.showSettings).toBe(true);
      act(() => result.current.closeSettings());
      expect(result.current.showSettings).toBe(false);
    });
  });

  describe("graph editor modal", () => {
    it("opens and closes", () => {
      const { result } = renderHook(() => useModalState());
      act(() => result.current.openGraphEditor());
      expect(result.current.graphEditing).toBe(true);
      act(() => result.current.closeGraphEditor());
      expect(result.current.graphEditing).toBe(false);
    });
  });

  describe("modal independence", () => {
    it("opening settings does not affect graph editor", () => {
      const { result } = renderHook(() => useModalState());
      act(() => result.current.openSettings());
      expect(result.current.showSettings).toBe(true);
      expect(result.current.graphEditing).toBe(false);
    });

    it("opening graph editor does not affect settings", () => {
      const { result } = renderHook(() => useModalState());
      act(() => result.current.openGraphEditor());
      expect(result.current.showSettings).toBe(false);
      expect(result.current.graphEditing).toBe(true);
    });
  });

  describe("state continuity", () => {
    it("preserves modal state across rerenders", () => {
      const { result, rerender } = renderHook(() => useModalState());
      act(() => result.current.openSettings());
      act(() => result.current.openGraphEditor());
      rerender();
      expect(result.current.showSettings).toBe(true);
      expect(result.current.graphEditing).toBe(true);
    });
  });
});

describe("the settings modal", () => {
  it("opens on the model stages, not on the actions that delete data", () => {
    const { result } = renderHook(() => useModalState());
    act(() => {
      result.current.openSettings();
    });
    expect(result.current.settingsTab).toBe("model");
  });

  it("opens on the tab a caller names", () => {
    const { result } = renderHook(() => useModalState());
    act(() => {
      result.current.openSettings("memory");
    });
    expect(result.current.settingsTab).toBe("memory");
  });
});

describe("a focused memory", () => {
  it("opens the settings modal on the memory tab", () => {
    const { result } = renderHook(() => useModalState());
    act(() => useMemoryFocusStore.getState().focusMemory("case:9b73", "case"));
    expect(result.current.showSettings).toBe(true);
    expect(result.current.settingsTab).toBe("memory");
  });

  it("is dropped when the modal closes", () => {
    const { result } = renderHook(() => useModalState());
    act(() => useMemoryFocusStore.getState().focusMemory("case:9b73", "case"));
    act(() => result.current.closeSettings());
    expect(result.current.showSettings).toBe(false);
    expect(useMemoryFocusStore.getState().focused).toBeNull();
  });

  it("is dropped by a tab change, which keeps the modal open on that tab", () => {
    const { result } = renderHook(() => useModalState());
    act(() => useMemoryFocusStore.getState().focusMemory("case:9b73", "case"));
    act(() => result.current.setSettingsTab("model"));
    expect(result.current.showSettings).toBe(true);
    expect(result.current.settingsTab).toBe("model");
    expect(useMemoryFocusStore.getState().focused).toBeNull();
  });
});
