/**
 * @vitest-environment jsdom
 */
import { renderHook } from "@testing-library/react";
import { act } from "react";
import { beforeEach, describe, expect, it } from "vitest";

import { useAutoCollapsePanels } from "./useAutoCollapsePanels";
import { useLeftSidebarStore, useRightRailStore } from "@/state/useRightRailStore";

const CONVERSATION = "c1";

function setViewport(width: number): void {
  window.innerWidth = width;
}

function openBothPanels(): void {
  useLeftSidebarStore.setState({ collapsed: false });
  useRightRailStore.getState().openPanelId(CONVERSATION, "tasks", { taskCount: 1 });
}

beforeEach(() => {
  setViewport(1400);
  openBothPanels();
});

describe("useAutoCollapsePanels", () => {
  it("closes the left sidebar and the right rail on a narrow viewport", () => {
    setViewport(820);

    renderHook(() => useAutoCollapsePanels());

    expect(useLeftSidebarStore.getState().collapsed).toBe(true);
    expect(useRightRailStore.getState().openPanel).toBeNull();
  });

  it("keeps both open on a wide viewport", () => {
    renderHook(() => useAutoCollapsePanels());

    expect(useLeftSidebarStore.getState().collapsed).toBe(false);
    expect(useRightRailStore.getState().openPanel).toBe("tasks");
  });

  it("closes both when the window narrows after mount", () => {
    renderHook(() => useAutoCollapsePanels());
    expect(useRightRailStore.getState().openPanel).toBe("tasks");

    setViewport(700);
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });

    expect(useLeftSidebarStore.getState().collapsed).toBe(true);
    expect(useRightRailStore.getState().openPanel).toBeNull();
  });

  it("leaves a panel the reader opens on a narrow viewport alone until the next resize", () => {
    setViewport(820);
    renderHook(() => useAutoCollapsePanels());
    expect(useRightRailStore.getState().openPanel).toBeNull();

    act(() => {
      useRightRailStore
        .getState()
        .openPanelId(CONVERSATION, "ledger", { ledgerCount: 2 });
    });

    expect(useRightRailStore.getState().openPanel).toBe("ledger");
  });
});
