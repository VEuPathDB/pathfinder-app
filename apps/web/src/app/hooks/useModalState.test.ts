/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useModalState } from "./useModalState";

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
