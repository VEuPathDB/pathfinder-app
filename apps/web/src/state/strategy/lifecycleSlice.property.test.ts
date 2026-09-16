import { beforeEach, describe, expect, it } from "vitest";
import fc from "fast-check";
import { useStrategyStore } from "./store";

type Cmd =
  | { kind: "init"; stepId: string }
  | { kind: "remove"; stepId: string }
  | { kind: "validate"; stepId: string }
  | { kind: "validateOk"; stepId: string; size: number | null }
  | { kind: "runCounts"; stepId: string }
  | { kind: "countsReady"; stepId: string; count: number | null };

const stepIdArb = fc.constantFrom("s1", "s2", "s3", "s4");

const cmdArb: fc.Arbitrary<Cmd> = fc.oneof(
  fc.record({ kind: fc.constant("init" as const), stepId: stepIdArb }),
  fc.record({ kind: fc.constant("remove" as const), stepId: stepIdArb }),
  fc.record({ kind: fc.constant("validate" as const), stepId: stepIdArb }),
  fc.record({
    kind: fc.constant("validateOk" as const),
    stepId: stepIdArb,
    size: fc.oneof(fc.constant(null), fc.integer({ min: 0, max: 1_000_000 })),
  }),
  fc.record({ kind: fc.constant("runCounts" as const), stepId: stepIdArb }),
  fc.record({
    kind: fc.constant("countsReady" as const),
    stepId: stepIdArb,
    count: fc.oneof(fc.constant(null), fc.integer({ min: 0, max: 1_000_000 })),
  }),
);

const VALID_STATES = new Set([
  "idle",
  "validating",
  "valid",
  "invalid",
  "running",
  "complete",
  "failed",
]);

function resetStore() {
  useStrategyStore.setState({ stepLifecycleById: {}, undoStack: [], redoStack: [] });
}

describe("lifecycleSlice - properties", () => {
  beforeEach(resetStore);

  it("every present step has a valid state name and getStepLifecycle is consistent with the map", () => {
    fc.assert(
      fc.property(fc.array(cmdArb, { minLength: 0, maxLength: 60 }), (cmds) => {
        resetStore();
        for (const cmd of cmds) {
          const api = useStrategyStore.getState();
          if (cmd.kind === "init") {
            api.initStepLifecycle(cmd.stepId);
          } else if (cmd.kind === "remove") {
            api.removeStepLifecycle(cmd.stepId);
          } else if (cmd.kind === "validate") {
            api.dispatchStepEvent(cmd.stepId, { type: "VALIDATE" });
          } else if (cmd.kind === "validateOk") {
            api.dispatchStepEvent(cmd.stepId, { type: "VALIDATE" });
            api.dispatchStepEvent(cmd.stepId, {
              type: "VALIDATION_SUCCESS",
              estimatedSize: cmd.size,
            });
          } else if (cmd.kind === "runCounts") {
            api.dispatchStepEvent(cmd.stepId, { type: "RUN_COUNTS" });
          } else {
            api.dispatchStepEvent(cmd.stepId, {
              type: "COUNTS_READY",
              count: cmd.count,
            });
          }
          // Invariants:
          //  1. Every entry in stepLifecycleById has a valid state name.
          //  2. getStepLifecycle returns the same snapshot the map holds.
          //  3. After a successful remove, getStepLifecycle returns null.
          const map = useStrategyStore.getState().stepLifecycleById;
          for (const [id, snap] of Object.entries(map)) {
            expect(VALID_STATES.has(String(snap.value))).toBe(true);
            expect(useStrategyStore.getState().getStepLifecycle(id)).toBe(snap);
          }
          if (cmd.kind === "remove") {
            expect(map[cmd.stepId]).toBeUndefined();
            expect(useStrategyStore.getState().getStepLifecycle(cmd.stepId)).toBeNull();
          }
        }
      }),
      { numRuns: 60 },
    );
  });
});
