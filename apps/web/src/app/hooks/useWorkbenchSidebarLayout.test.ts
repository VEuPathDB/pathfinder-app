/**
 * @vitest-environment jsdom
 */
import { renderHook } from "@testing-library/react";
import { act } from "react";
import { beforeEach, describe, expect, it } from "vitest";

import {
  WORKBENCH_SIDEBAR_WIDTH_PX,
  WORKBENCH_SIDE_CHROME_PX,
  useWorkbenchSidebarLayout,
  workbenchSidebarWidth,
} from "./useWorkbenchSidebarLayout";
import { useWorkbenchStore } from "@/state/useWorkbenchStore";

const PHONE = 390;
const DESKTOP = 1440;

function setViewport(width: number): void {
  window.innerWidth = width;
}

beforeEach(() => {
  setViewport(DESKTOP);
  useWorkbenchStore.setState({ leftSidebarOpen: true, geneSearchOpen: true });
});

describe("workbenchSidebarWidth", () => {
  it("gives the panel its full width on a desktop viewport", () => {
    expect(workbenchSidebarWidth(DESKTOP)).toBe(WORKBENCH_SIDEBAR_WIDTH_PX);
  });

  it("keeps the whole panel on screen at phone width", () => {
    expect(workbenchSidebarWidth(PHONE)).toBe(PHONE - WORKBENCH_SIDE_CHROME_PX);
    expect(workbenchSidebarWidth(PHONE) + WORKBENCH_SIDE_CHROME_PX).toBeLessThanOrEqual(
      PHONE,
    );
  });

  it("never reports a negative width", () => {
    expect(workbenchSidebarWidth(40)).toBe(0);
  });
});

describe("useWorkbenchSidebarLayout", () => {
  it("reports the capped width for the current viewport", () => {
    setViewport(PHONE);

    const { result } = renderHook(() => useWorkbenchSidebarLayout());

    expect(result.current).toBe(PHONE - WORKBENCH_SIDE_CHROME_PX);
  });

  it("closes both workbench panels on a phone viewport", () => {
    setViewport(PHONE);

    renderHook(() => useWorkbenchSidebarLayout());

    expect(useWorkbenchStore.getState().leftSidebarOpen).toBe(false);
    expect(useWorkbenchStore.getState().geneSearchOpen).toBe(false);
  });

  it("leaves both panels open on a desktop viewport", () => {
    renderHook(() => useWorkbenchSidebarLayout());

    expect(useWorkbenchStore.getState().leftSidebarOpen).toBe(true);
    expect(useWorkbenchStore.getState().geneSearchOpen).toBe(true);
  });

  it("closes them and re-measures when the window narrows after mount", () => {
    const { result, rerender } = renderHook(() => useWorkbenchSidebarLayout());
    expect(result.current).toBe(WORKBENCH_SIDEBAR_WIDTH_PX);

    setViewport(PHONE);
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });
    rerender();

    expect(useWorkbenchStore.getState().leftSidebarOpen).toBe(false);
    expect(result.current).toBe(PHONE - WORKBENCH_SIDE_CHROME_PX);
  });
});
