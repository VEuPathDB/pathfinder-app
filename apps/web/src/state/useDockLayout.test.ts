// @vitest-environment jsdom
import { renderHook } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";

import { LeftSidebarDrawn, railMayOpenItself, useDockLayout } from "./useDockLayout";
import {
  useLeftSidebarStore,
  useRightRailStore,
  useSideOrderStore,
} from "./useRightRailStore";

beforeEach(() => {
  useLeftSidebarStore.setState({ collapsed: false, width: 360 });
  useRightRailStore.setState({ openPanel: "review" });
  useSideOrderStore.setState({ lastOpened: "right" });
});

function withSidebar({ children }: { children: ReactNode }) {
  return createElement(LeftSidebarDrawn, { value: true }, children);
}

describe("useDockLayout", () => {
  it("floats the rail opened last in a window that cannot hold both", () => {
    window.innerWidth = 1200;
    const { result } = renderHook(() => useDockLayout(), { wrapper: withSidebar });
    expect(result.current).toEqual({ leftFloats: false, rightFloats: true });
  });

  it("docks both in a wide window", () => {
    window.innerWidth = 1600;
    const { result } = renderHook(() => useDockLayout(), { wrapper: withSidebar });
    expect(result.current).toEqual({ leftFloats: false, rightFloats: false });
  });

  it("docks the rail on a page that draws no sidebar, whatever the stored sidebar says", () => {
    window.innerWidth = 1200;
    const { result } = renderHook(() => useDockLayout());
    expect(result.current).toEqual({ leftFloats: false, rightFloats: false });
  });
});

describe("railMayOpenItself", () => {
  it("refuses when the rail would float over the chat", () => {
    useRightRailStore.setState({ openPanel: null });
    window.innerWidth = 1280;
    expect(railMayOpenItself(true)).toBe(false);
  });

  it("allows on a page that draws no sidebar where the sidebar would have crowded it", () => {
    useRightRailStore.setState({ openPanel: null });
    window.innerWidth = 1280;
    expect(railMayOpenItself(false)).toBe(true);
  });

  it("allows when the rail docks beside the chat", () => {
    useRightRailStore.setState({ openPanel: null });
    window.innerWidth = 1600;
    expect(railMayOpenItself(true)).toBe(true);
  });
});
