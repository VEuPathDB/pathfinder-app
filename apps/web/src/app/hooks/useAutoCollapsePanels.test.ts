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
  useRightRailStore.getState().openPanelId(CONVERSATION, "review", { reviewCount: 1 });
}

beforeEach(() => {
  setViewport(1400);
  openBothPanels();
});

describe("useAutoCollapsePanels", () => {
  it("closes the left sidebar and the right rail on a narrow viewport", () => {
    setViewport(820);

    renderHook(() => useAutoCollapsePanels("/conversation/c1"));

    expect(useLeftSidebarStore.getState().collapsed).toBe(true);
    expect(useRightRailStore.getState().openPanel).toBeNull();
  });

  it("keeps both open on a wide viewport", () => {
    renderHook(() => useAutoCollapsePanels("/conversation/c1"));

    expect(useLeftSidebarStore.getState().collapsed).toBe(false);
    expect(useRightRailStore.getState().openPanel).toBe("review");
  });

  it("closes both when the window narrows after mount", () => {
    renderHook(() => useAutoCollapsePanels("/conversation/c1"));
    expect(useRightRailStore.getState().openPanel).toBe("review");

    setViewport(700);
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });

    expect(useLeftSidebarStore.getState().collapsed).toBe(true);
    expect(useRightRailStore.getState().openPanel).toBeNull();
  });

  it("leaves a panel the reader opens on a narrow viewport alone until the next resize", () => {
    setViewport(820);
    renderHook(() => useAutoCollapsePanels("/conversation/c1"));
    expect(useRightRailStore.getState().openPanel).toBeNull();

    act(() => {
      useRightRailStore
        .getState()
        .openPanelId(CONVERSATION, "review", { reviewCount: 2 });
    });

    expect(useRightRailStore.getState().openPanel).toBe("review");
  });

  it("closes both drawers when a narrow window moves to another page", async () => {
    setViewport(390);
    const view = renderHook((path: string) => useAutoCollapsePanels(path), {
      initialProps: "/conversation/c1",
    });
    act(openBothPanels);

    await act(async () => {
      view.rerender("/conversation/c2");
    });

    expect(useLeftSidebarStore.getState().collapsed).toBe(true);
    expect(useRightRailStore.getState().openPanel).toBeNull();
  });

  it("keeps a drawer the reader opened through a resize that leaves it floating", () => {
    setViewport(980);
    useLeftSidebarStore.setState({ collapsed: true });
    useRightRailStore.getState().closePanel();
    renderHook(() => useAutoCollapsePanels("/conversation/c1"));
    act(() => {
      useRightRailStore.getState().openPanelId(CONVERSATION, "review", {});
    });

    setViewport(960);
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });

    expect(useRightRailStore.getState().openPanel).toBe("review");
  });

  it("closes a docked rail that a narrowing window turns into a drawer", () => {
    useLeftSidebarStore.setState({ collapsed: true });
    renderHook(() => useAutoCollapsePanels("/conversation/c1"));

    setViewport(980);
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });

    expect(useRightRailStore.getState().openPanel).toBe(null);
  });

  it("closes only the floating rail when a mid-width window moves to another page", async () => {
    setViewport(1200);
    const view = renderHook((path: string) => useAutoCollapsePanels(path), {
      initialProps: "/conversation/c1",
    });
    act(openBothPanels);

    await act(async () => {
      view.rerender("/conversation/c2");
    });

    expect([
      useLeftSidebarStore.getState().collapsed,
      useRightRailStore.getState().openPanel,
    ]).toEqual([false, null]);
  });

  it("keeps both open when a wide window moves to another page", async () => {
    const view = renderHook((path: string) => useAutoCollapsePanels(path), {
      initialProps: "/conversation/c1",
    });

    await act(async () => {
      view.rerender("/conversation/c2");
    });

    expect(useLeftSidebarStore.getState().collapsed).toBe(false);
    expect(useRightRailStore.getState().openPanel).toBe("review");
  });
});
