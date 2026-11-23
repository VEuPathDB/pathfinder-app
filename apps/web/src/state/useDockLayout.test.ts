// @vitest-environment jsdom
import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { railMayOpenItself, useDockLayout } from "./useDockLayout";
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

describe("useDockLayout", () => {
  it("floats the rail opened last in a window that cannot hold both", () => {
    window.innerWidth = 1200;
    const { result } = renderHook(() => useDockLayout());
    expect(result.current).toEqual({ leftFloats: false, rightFloats: true });
  });

  it("docks both in a wide window", () => {
    window.innerWidth = 1600;
    const { result } = renderHook(() => useDockLayout());
    expect(result.current).toEqual({ leftFloats: false, rightFloats: false });
  });
});

describe("railMayOpenItself", () => {
  it("refuses when the rail would float over the chat", () => {
    useRightRailStore.setState({ openPanel: null });
    window.innerWidth = 1280;
    expect(railMayOpenItself()).toBe(false);
  });

  it("allows when the rail docks beside the chat", () => {
    useRightRailStore.setState({ openPanel: null });
    window.innerWidth = 1600;
    expect(railMayOpenItself()).toBe(true);
  });
});
