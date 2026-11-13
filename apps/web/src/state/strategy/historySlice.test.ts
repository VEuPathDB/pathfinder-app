import { beforeEach, describe, expect, it } from "vitest";
import type { Step, Strategy } from "@strategist/shared";
import { useStrategyStore } from "./store";

function step(partial: Partial<Step> & { id: string; displayName: string }): Step {
  return { isFiltered: false, ...partial };
}

function makeStrategy(steps: Step[]): Strategy {
  return {
    id: "strategy-1",
    name: "Test",
    siteId: "plasmodb",
    recordType: "gene",
    steps,
    rootStepId: steps[steps.length - 1]?.id ?? null,
    isSaved: false,
    description: null,
    wdkStrategyId: null,
    wdkUrl: null,
    createdAt: "2026-01-01T00:00:00.000Z",
    updatedAt: "2026-01-01T00:00:00.000Z",
  };
}

function rename(strategy: Strategy, id: string, name: string): Strategy {
  return {
    ...strategy,
    steps: strategy.steps.map((s) => (s.id === id ? { ...s, displayName: name } : s)),
  };
}

function removeStepById(strategy: Strategy, id: string): Strategy {
  return { ...strategy, steps: strategy.steps.filter((s) => s.id !== id) };
}

describe("state/strategy/historySlice (TQ-cache aware: pure patch logic)", () => {
  beforeEach(() => {
    useStrategyStore.getState().clear();
  });

  it("pushSnapshot stores inverse patches required to undo back to prev", () => {
    const { pushSnapshot } = useStrategyStore.getState();
    const prev = makeStrategy([
      step({
        id: "s1",
        displayName: "Search 1",
        searchName: "geneById",
        recordType: "gene",
      }),
    ]);
    const next = rename(prev, "s1", "Renamed");
    pushSnapshot({ strategy: prev }, next);

    const { undoStack, redoStack } = useStrategyStore.getState();
    expect(undoStack).toHaveLength(1);
    expect(redoStack).toHaveLength(0);
    expect(undoStack[0]?.length).toBeGreaterThan(0);
  });

  it("dropSnapshot keeps the redo entry of an edit already undone", () => {
    const store = useStrategyStore.getState();
    const prev = makeStrategy([step({ id: "s1", displayName: "Search 1" })]);
    const next = rename(prev, "s1", "Renamed");
    const pushed = store.pushSnapshot({ strategy: prev }, next);
    store.undo(next);
    const { redoStack } = useStrategyStore.getState();
    expect(redoStack).toHaveLength(1);

    store.dropSnapshot(pushed ?? []);

    expect(useStrategyStore.getState().redoStack).toEqual(redoStack);
  });

  it("pushSnapshot is a no-op when prev.strategy is null", () => {
    const { pushSnapshot } = useStrategyStore.getState();
    const next = makeStrategy([
      step({ id: "s1", displayName: "S1", searchName: "geneById", recordType: "gene" }),
    ]);
    pushSnapshot({ strategy: null }, next);
    expect(useStrategyStore.getState().undoStack).toHaveLength(0);
  });

  it("undo applies the inverse to the supplied current and returns the prior strategy", () => {
    const { pushSnapshot, undo } = useStrategyStore.getState();
    const prev = makeStrategy([
      step({
        id: "s1",
        displayName: "Search 1",
        searchName: "geneById",
        recordType: "gene",
      }),
    ]);
    const next = rename(prev, "s1", "Renamed");
    pushSnapshot({ strategy: prev }, next);

    const restored = undo(next);
    expect(restored?.steps[0]?.displayName).toBe("Search 1");
    expect(useStrategyStore.getState().redoStack).toHaveLength(1);
    expect(useStrategyStore.getState().undoStack).toHaveLength(0);
  });

  it("redo applies the forward patch and returns the new strategy", () => {
    const { pushSnapshot, undo, redo } = useStrategyStore.getState();
    const prev = makeStrategy([
      step({
        id: "s1",
        displayName: "Search 1",
        searchName: "geneById",
        recordType: "gene",
      }),
    ]);
    const next = rename(prev, "s1", "Renamed");
    pushSnapshot({ strategy: prev }, next);
    const after = undo(next);
    const redone = redo(after);
    expect(redone?.steps[0]?.displayName).toBe("Renamed");
    expect(useStrategyStore.getState().undoStack).toHaveLength(1);
    expect(useStrategyStore.getState().redoStack).toHaveLength(0);
  });

  it("new pushSnapshot after undo clears redoStack", () => {
    const { pushSnapshot, undo } = useStrategyStore.getState();
    const a = makeStrategy([
      step({
        id: "s1",
        displayName: "Search 1",
        searchName: "geneById",
        recordType: "gene",
      }),
    ]);
    const b = rename(a, "s1", "Renamed");
    pushSnapshot({ strategy: a }, b);
    const afterUndo = undo(b);
    expect(useStrategyStore.getState().redoStack).toHaveLength(1);
    expect(afterUndo?.steps[0]?.displayName).toBe("Search 1");

    const c = rename(afterUndo!, "s1", "Fresh");
    pushSnapshot({ strategy: afterUndo }, c);
    expect(useStrategyStore.getState().redoStack).toHaveLength(0);
    expect(useStrategyStore.getState().undoStack).toHaveLength(1);
  });

  it("undo/redo roundtrips a step removal", () => {
    const { pushSnapshot, undo, redo } = useStrategyStore.getState();
    const prev = makeStrategy([
      step({ id: "s1", displayName: "S1", searchName: "geneById", recordType: "gene" }),
      step({ id: "s2", displayName: "S2", searchName: "geneById", recordType: "gene" }),
    ]);
    const next = removeStepById(prev, "s1");
    pushSnapshot({ strategy: prev }, next);

    const restored = undo(next);
    expect(restored?.steps.find((s) => s.id === "s1")?.displayName).toBe("S1");
    const redone = redo(restored);
    expect(redone?.steps.find((s) => s.id === "s1")).toBeUndefined();
  });

  it("caps undoStack at MAX_HISTORY (50)", () => {
    const { pushSnapshot } = useStrategyStore.getState();
    let current = makeStrategy([
      step({
        id: "s1",
        displayName: "init",
        searchName: "geneById",
        recordType: "gene",
      }),
    ]);
    for (let i = 0; i < 60; i += 1) {
      const next = rename(current, "s1", `name-${i}`);
      pushSnapshot({ strategy: current }, next);
      current = next;
    }
    expect(useStrategyStore.getState().undoStack.length).toBe(50);
  });

  it("clear empties both stacks", () => {
    const { pushSnapshot, clear } = useStrategyStore.getState();
    const a = makeStrategy([
      step({ id: "s1", displayName: "S1", searchName: "geneById", recordType: "gene" }),
    ]);
    pushSnapshot({ strategy: a }, rename(a, "s1", "R"));
    clear();
    expect(useStrategyStore.getState().undoStack).toHaveLength(0);
    expect(useStrategyStore.getState().redoStack).toHaveLength(0);
  });

  it("undo returns null when undoStack is empty", () => {
    const { undo } = useStrategyStore.getState();
    expect(undo(null)).toBeNull();
    expect(useStrategyStore.getState().undoStack).toHaveLength(0);
  });

  it("redo returns null when redoStack is empty", () => {
    const { redo } = useStrategyStore.getState();
    expect(redo(null)).toBeNull();
    expect(useStrategyStore.getState().redoStack).toHaveLength(0);
  });

  it("persists step data integrity across multiple undo/redo cycles", () => {
    const { pushSnapshot, undo, redo } = useStrategyStore.getState();
    const a = makeStrategy([
      step({ id: "s1", displayName: "S1", searchName: "geneById", recordType: "gene" }),
    ]);
    const b = rename(a, "s1", "Second");
    pushSnapshot({ strategy: a }, b);
    const c = rename(b, "s1", "Third");
    pushSnapshot({ strategy: b }, c);

    const undo1 = undo(c);
    expect(undo1?.steps[0]?.displayName).toBe("Second");
    const undo2 = undo(undo1);
    expect(undo2?.steps[0]?.displayName).toBe("S1");
    const redo1 = redo(undo2);
    expect(redo1?.steps[0]?.displayName).toBe("Second");
    const redo2 = redo(redo1);
    expect(redo2?.steps[0]?.displayName).toBe("Third");
  });

  it("pushSnapshot is a no-op when nothing changed", () => {
    const { pushSnapshot } = useStrategyStore.getState();
    const a = makeStrategy([
      step({ id: "s1", displayName: "S1", searchName: "geneById", recordType: "gene" }),
    ]);
    pushSnapshot({ strategy: a }, a);
    expect(useStrategyStore.getState().undoStack).toHaveLength(0);
  });

  it("canUndo is false on an empty stack, true once a snapshot is pushed, false again after undoing it", () => {
    expect(useStrategyStore.getState().canUndo()).toBe(false);
    const a = makeStrategy([
      step({ id: "s1", displayName: "S1", searchName: "geneById", recordType: "gene" }),
    ]);
    const b = rename(a, "s1", "Renamed");
    useStrategyStore.getState().pushSnapshot({ strategy: a }, b);
    expect(useStrategyStore.getState().canUndo()).toBe(true);
    useStrategyStore.getState().undo(b);
    expect(useStrategyStore.getState().canUndo()).toBe(false);
  });

  it("canRedo is false until something has been undone, and false again once redone", () => {
    expect(useStrategyStore.getState().canRedo()).toBe(false);
    const a = makeStrategy([
      step({ id: "s1", displayName: "S1", searchName: "geneById", recordType: "gene" }),
    ]);
    const b = rename(a, "s1", "Renamed");
    useStrategyStore.getState().pushSnapshot({ strategy: a }, b);
    expect(useStrategyStore.getState().canRedo()).toBe(false);
    const undone = useStrategyStore.getState().undo(b);
    expect(useStrategyStore.getState().canRedo()).toBe(true);
    useStrategyStore.getState().redo(undone);
    expect(useStrategyStore.getState().canRedo()).toBe(false);
  });

  it("clearHistory empties both stacks but leaves step lifecycles alone", () => {
    const a = makeStrategy([
      step({ id: "s1", displayName: "S1", searchName: "geneById", recordType: "gene" }),
    ]);
    const b = rename(a, "s1", "Renamed");
    useStrategyStore.getState().pushSnapshot({ strategy: a }, b);
    useStrategyStore.getState().undo(b);
    useStrategyStore.getState().initStepLifecycle("s1", { state: "valid" });
    expect(useStrategyStore.getState().undoStack).toHaveLength(0);
    expect(useStrategyStore.getState().redoStack).toHaveLength(1);

    useStrategyStore.getState().clearHistory();

    expect(useStrategyStore.getState().undoStack).toEqual([]);
    expect(useStrategyStore.getState().redoStack).toEqual([]);
    expect(useStrategyStore.getState().canUndo()).toBe(false);
    expect(useStrategyStore.getState().canRedo()).toBe(false);
    expect(useStrategyStore.getState().getStepLifecycle("s1")?.value).toBe("valid");
  });
});
