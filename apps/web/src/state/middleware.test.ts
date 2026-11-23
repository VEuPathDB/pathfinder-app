// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
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
});
