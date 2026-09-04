import { beforeEach, describe, expect, it } from "vitest";
import type { GraphOperation } from "@/lib/types/graphOperation";
import { useStrategyStore } from "./store";

const DELETE_OP: GraphOperation = {
  kind: "deleteStep",
  stepId: "s1",
  resolution: "collapse-combine",
};

describe("strategy store - setLastFailedOperation", () => {
  beforeEach(() => {
    useStrategyStore.getState().clear();
  });

  it("stores the failed operation so the retry affordance can replay it", () => {
    useStrategyStore.getState().setLastFailedOperation({ op: DELETE_OP });
    expect(useStrategyStore.getState().lastFailedOperation).toEqual({
      op: DELETE_OP,
    });
  });

  it("keeps only the most recent failure", () => {
    const api = useStrategyStore.getState();
    api.setLastFailedOperation({ op: DELETE_OP });
    const renameOp: GraphOperation = {
      kind: "updateStepMeta",
      stepId: "s2",
      displayName: "Renamed",
    };
    api.setLastFailedOperation({ op: renameOp });
    expect(useStrategyStore.getState().lastFailedOperation?.op).toEqual(renameOp);
  });

  it("clears the failure when passed null", () => {
    const api = useStrategyStore.getState();
    api.setLastFailedOperation({ op: DELETE_OP });
    api.setLastFailedOperation(null);
    expect(useStrategyStore.getState().lastFailedOperation).toBe(null);
  });

  it("does not disturb lifecycle or history state", () => {
    const api = useStrategyStore.getState();
    api.initStepLifecycle("s1", { state: "valid" });
    const lifecyclesBefore = useStrategyStore.getState().stepLifecycleById;
    api.setLastFailedOperation({ op: DELETE_OP });
    expect(useStrategyStore.getState().stepLifecycleById).toBe(lifecyclesBefore);
  });
});

describe("strategy store - clear", () => {
  beforeEach(() => {
    useStrategyStore.getState().clear();
  });

  it("resets the failed operation, every lifecycle and both history stacks", () => {
    const api = useStrategyStore.getState();
    api.setLastFailedOperation({ op: DELETE_OP });
    api.initStepLifecycle("s1", { state: "valid" });
    useStrategyStore.setState({ undoStack: [[]], redoStack: [[]] });

    useStrategyStore.getState().clear();

    const state = useStrategyStore.getState();
    expect(state.lastFailedOperation).toBe(null);
    expect(state.stepLifecycleById).toEqual({});
    expect(state.undoStack).toEqual([]);
    expect(state.redoStack).toEqual([]);
  });
});
