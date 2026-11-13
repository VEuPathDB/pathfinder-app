// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";
import { createStore, createPersistedStore } from "./middleware";

interface CountState {
  count: number;
  inc: () => void;
}

describe("state/middleware", () => {
  it("createStore returns a functional store with devtools", () => {
    const useTestStore = createStore<CountState>("TestStore", (set) => ({
      count: 0,
      inc: () => set((s) => ({ count: s.count + 1 })),
    }));

    expect(useTestStore.getState().count).toBe(0);
    useTestStore.getState().inc();
    expect(useTestStore.getState().count).toBe(1);
  });

  it("createPersistedStore returns a functional store", () => {
    const useTestStore = createPersistedStore<CountState>(
      "TestPersisted",
      (set) => ({
        count: 0,
        inc: () => set((s) => ({ count: s.count + 1 })),
      }),
      {
        name: "test-persisted-store",
        partialize: (s) => ({ count: s.count }),
      },
    );

    expect(useTestStore.getState().count).toBe(0);
    useTestStore.getState().inc();
    expect(useTestStore.getState().count).toBe(1);
  });

  describe("a store kept under the old product name", () => {
    beforeEach(() => {
      window.localStorage.clear();
    });

    const open = () =>
      createPersistedStore<CountState>(
        "Moved",
        (set) => ({ count: 0, inc: () => set((s) => ({ count: s.count + 1 })) }),
        { name: "strategist-moved", partialize: (s) => ({ count: s.count }) },
      );

    it("moves each current key and step draft to the new name", () => {
      window.localStorage.setItem("pathfinder-settings-20260625", '{"a":1}');
      window.localStorage.setItem("pathfinder.editor.draft.7.9", '{"x":2}');
      open();
      expect(window.localStorage.getItem("strategist-settings-20260625")).toBe(
        '{"a":1}',
      );
      expect(window.localStorage.getItem("strategist.editor.draft.7.9")).toBe(
        '{"x":2}',
      );
      expect(window.localStorage.getItem("pathfinder-settings-20260625")).toBeNull();
      expect(window.localStorage.getItem("pathfinder.editor.draft.7.9")).toBeNull();
    });

    it("keeps a value already saved under the new name", () => {
      window.localStorage.setItem("pathfinder-settings-20260625", '{"a":1}');
      window.localStorage.setItem("strategist-settings-20260625", '{"a":3}');
      open();
      expect(window.localStorage.getItem("strategist-settings-20260625")).toBe(
        '{"a":3}',
      );
      expect(window.localStorage.getItem("pathfinder-settings-20260625")).toBeNull();
    });

    it("drops a key from an earlier storage epoch", () => {
      window.localStorage.setItem("pathfinder-settings", '{"a":1}');
      window.localStorage.setItem("pathfinder:location", "x");
      open();
      const left = Array.from({ length: window.localStorage.length }, (_, i) =>
        window.localStorage.key(i),
      );
      expect(left).toEqual([]);
    });
  });
});
