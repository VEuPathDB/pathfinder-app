// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { useLeftSidebarStore, useRightRailStore } from "@/state/useRightRailStore";

import { useSidebarResize } from "./useSidebarResize";

function container(width: number): HTMLDivElement {
  const element = document.createElement("div");
  element.getBoundingClientRect = () => new DOMRect(0, 0, width, 800);
  return element;
}

beforeEach(() => {
  useLeftSidebarStore.setState({ collapsed: false, width: 280 });
  useRightRailStore.setState({ openPanel: "review" });
});

describe("useSidebarResize", () => {
  it("stops the drag where the chat would drop below 600px beside an open panel", () => {
    const { result } = renderHook(() => useSidebarResize());
    result.current.layoutRef.current = container(1300);

    act(() => result.current.startDragging());
    act(() => {
      window.dispatchEvent(new MouseEvent("mousemove", { clientX: 340 }));
    });

    expect(useLeftSidebarStore.getState().width).toBe(292);
  });
});
