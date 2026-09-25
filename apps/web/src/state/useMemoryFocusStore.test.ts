import { afterEach, describe, expect, it } from "vitest";

import { useMemoryFocusStore } from "./useMemoryFocusStore";

afterEach(() => {
  useMemoryFocusStore.getState().clearFocus();
});

describe("useMemoryFocusStore", () => {
  it("starts with no memory in focus", () => {
    expect(useMemoryFocusStore.getState()).toMatchObject({ focused: null });
  });

  it("holds the key and kind of the memory a caller focuses", () => {
    useMemoryFocusStore.getState().focusMemory("case:9b73", "case");
    expect(useMemoryFocusStore.getState().focused).toEqual({
      key: "case:9b73",
      kind: "case",
    });
  });

  it("drops the focus when cleared", () => {
    useMemoryFocusStore.getState().focusMemory("case:9b73", "case");
    useMemoryFocusStore.getState().clearFocus();
    expect(useMemoryFocusStore.getState()).toMatchObject({ focused: null });
  });
});
