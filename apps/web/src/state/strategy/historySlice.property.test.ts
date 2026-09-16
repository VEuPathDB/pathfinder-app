import { beforeEach, describe, expect, it } from "vitest";
import fc from "fast-check";
import type { Step, Strategy } from "@pathfinder/shared";
import { useStrategyStore } from "./store";

const MAX_HISTORY = 50;

function makeStrategy(name: string): Strategy {
  const step: Step = {
    id: "s1",
    displayName: name,
    searchName: "geneById",
    recordType: "gene",
    isFiltered: false,
  };
  return {
    id: "strategy-1",
    name: "Test",
    siteId: "plasmodb",
    recordType: "gene",
    steps: [step],
    rootStepId: "s1",
    isSaved: false,
    description: null,
    wdkStrategyId: null,
    wdkUrl: null,
    createdAt: "2026-01-01T00:00:00.000Z",
    updatedAt: "2026-01-01T00:00:00.000Z",
  };
}

type Action =
  | { kind: "push"; name: string }
  | { kind: "undo" }
  | { kind: "redo" }
  | { kind: "clearHistory" };

const actionArb: fc.Arbitrary<Action> = fc.oneof(
  fc
    .string({ minLength: 1, maxLength: 16 })
    .map((name) => ({ kind: "push" as const, name })),
  fc.constant({ kind: "undo" as const }),
  fc.constant({ kind: "redo" as const }),
  fc.constant({ kind: "clearHistory" as const }),
);

describe("historySlice - properties", () => {
  beforeEach(() => {
    useStrategyStore.getState().clear();
  });

  it("undoStack length never exceeds MAX_HISTORY across arbitrary action sequences", () => {
    fc.assert(
      fc.property(fc.array(actionArb, { minLength: 0, maxLength: 200 }), (actions) => {
        useStrategyStore.getState().clear();
        let current: Strategy = makeStrategy("init");
        for (const action of actions) {
          const api = useStrategyStore.getState();
          if (action.kind === "push") {
            const next = makeStrategy(action.name);
            api.pushSnapshot({ strategy: current }, next);
            current = next;
          } else if (action.kind === "undo") {
            const restored = api.undo(current);
            if (restored !== null) current = restored;
          } else if (action.kind === "redo") {
            const restored = api.redo(current);
            if (restored !== null) current = restored;
          } else {
            api.clearHistory();
          }
          const { undoStack, redoStack } = useStrategyStore.getState();
          expect(undoStack.length).toBeLessThanOrEqual(MAX_HISTORY);
          expect(redoStack.length).toBeLessThanOrEqual(MAX_HISTORY);
        }
      }),
      { numRuns: 75 },
    );
  });

  it("undo immediately followed by redo round-trips to the same strategy", () => {
    const namesArb = fc.array(fc.string({ minLength: 1, maxLength: 16 }), {
      minLength: 1,
      maxLength: 20,
    });
    fc.assert(
      fc.property(namesArb, (names) => {
        useStrategyStore.getState().clear();
        let current: Strategy = makeStrategy("init");
        const api = useStrategyStore.getState();
        for (const n of names) {
          const next = makeStrategy(n);
          api.pushSnapshot({ strategy: current }, next);
          current = next;
        }
        // Snapshot the post-push current.
        const post: Strategy = current;
        // undo then redo (only meaningful if undo non-null).
        const after = useStrategyStore.getState().undo(post);
        if (after === null) return;
        const back = useStrategyStore.getState().redo(after);
        expect(back).not.toBeNull();
        expect(back?.steps[0]?.displayName).toBe(post.steps[0]?.displayName);
      }),
      { numRuns: 60 },
    );
  });
});
