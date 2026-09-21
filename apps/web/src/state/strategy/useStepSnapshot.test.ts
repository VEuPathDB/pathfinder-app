/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";
import type { Step } from "@pathfinder/shared";
import { useStrategyStore } from "./store";
import { STEP_LIFECYCLE_STATE_NAMES, seedStepMachine } from "./stepMachine";
import { useStepSnapshot } from "./useStepSnapshot";

function makeStep(overrides: Partial<Step> = {}): Step {
  return {
    id: "s1",
    displayName: "Step 1",
    searchName: "GenesByTaxon",
    recordType: "gene",
    parameters: {},
    estimatedSize: null,
    isFiltered: false,
    validation: null,
    ...overrides,
  };
}

function resetStore() {
  useStrategyStore.setState({
    stepLifecycleById: {},
    undoStack: [],
    redoStack: [],
  });
}

describe("useStepSnapshot", () => {
  beforeEach(resetStore);

  it("defaults to idle with null values for a null step", () => {
    const { result } = renderHook(() => useStepSnapshot(null));
    expect(result.current.step).toBe(null);
    expect(result.current.lifecycleState).toBe("idle");
    expect(result.current.estimatedSize).toBe(null);
    expect(result.current.validationErrors).toBe(null);
    expect(result.current.isBusy).toBe(false);
    expect(result.current.isInvalid).toBe(false);
    expect(result.current.isFailed).toBe(false);
  });

  it("returns wire estimatedSize when no lifecycle context override", () => {
    const step = makeStep({ estimatedSize: 99 });
    const { result } = renderHook(() => useStepSnapshot(step));
    expect(result.current.estimatedSize).toBe(99);
  });

  it("the wire count wins over one the machine cached earlier", () => {
    // The machine's cache is what let a count the canvas computed once mask
    // every later value the server sent.
    const step = makeStep({ estimatedSize: 71 });
    useStrategyStore.getState().applyStepCounts({ s1: 0 });
    const { result } = renderHook(() => useStepSnapshot(step));
    expect(result.current.estimatedSize).toBe(71);
    expect(result.current.lifecycleState).toBe("complete");
  });

  it("uses the machine count for a step the wire does not count", () => {
    const step = makeStep({ estimatedSize: null });
    useStrategyStore.getState().applyStepCounts({ s1: 500 });
    const { result } = renderHook(() => useStepSnapshot(step));
    expect(result.current.estimatedSize).toBe(500);
  });

  it("surfaces invalid state and validation errors", () => {
    const step = makeStep();
    useStrategyStore.getState().applyStepValidationErrors({ s1: "Missing taxon" });
    const { result } = renderHook(() => useStepSnapshot(step));
    expect(result.current.isInvalid).toBe(true);
    expect(result.current.validationErrors?.general?.[0]).toBe("Missing taxon");
  });

  it("surfaces failed state with lastError", () => {
    const step = makeStep();
    const api = useStrategyStore.getState();
    api.dispatchStepEvent("s1", { type: "VALIDATE" });
    api.dispatchStepEvent("s1", { type: "VALIDATION_SUCCESS" });
    api.dispatchStepEvent("s1", { type: "RUN_COUNTS" });
    api.dispatchStepEvent("s1", { type: "RUN_ERROR", message: "500" });
    const { result } = renderHook(() => useStepSnapshot(step));
    expect(result.current.isFailed).toBe(true);
    expect(result.current.lastError).toBe("500");
  });

  it("isBusy true during validating / running", () => {
    const step = makeStep();
    const api = useStrategyStore.getState();
    api.initStepLifecycle("s1");
    api.dispatchStepEvent("s1", { type: "VALIDATE" });
    const { result, rerender } = renderHook(() => useStepSnapshot(step));
    expect(result.current.isBusy).toBe(true);
    api.dispatchStepEvent("s1", { type: "VALIDATION_SUCCESS" });
    rerender();
    expect(result.current.isBusy).toBe(false);
  });

  it("falls back to wire validation.errors when lifecycle has none", () => {
    const step = makeStep({
      validation: {
        level: "UNRUNNABLE",
        isValid: false,
        errors: { general: ["Server said no"], byKey: {} },
      },
    });
    const { result } = renderHook(() => useStepSnapshot(step));
    expect(result.current.validationErrors?.general?.[0]).toBe("Server said no");
  });

  it("falls back to the wire estimatedSize when a lifecycle exists but has cached no count", () => {
    const step = makeStep({ estimatedSize: 99 });
    useStrategyStore.getState().initStepLifecycle("s1");
    const { result } = renderHook(() => useStepSnapshot(step));
    expect(result.current.lifecycleState).toBe("idle");
    expect(result.current.estimatedSize).toBe(99);
  });

  it("isBusy is true while counts are running", () => {
    const step = makeStep();
    const api = useStrategyStore.getState();
    api.initStepLifecycle("s1", { state: "valid" });
    api.dispatchStepEvent("s1", { type: "RUN_COUNTS" });
    const { result } = renderHook(() => useStepSnapshot(step));
    expect(result.current.lifecycleState).toBe("running");
    expect(result.current.isBusy).toBe(true);
    expect(result.current.isInvalid).toBe(false);
    expect(result.current.isFailed).toBe(false);
  });

  it("a null step never adopts a lifecycle stored under the empty step id", () => {
    useStrategyStore.getState().dispatchStepEvent("", { type: "VALIDATE" });
    const { result } = renderHook(() => useStepSnapshot(null));
    expect(result.current.lifecycleState).toBe("idle");
    expect(result.current.isBusy).toBe(false);
  });

  it("normalizes wire validation errors that omit general and byKey", () => {
    const step = makeStep({
      validation: { level: "UNRUNNABLE", isValid: false, errors: {} },
    });
    const { result } = renderHook(() => useStepSnapshot(step));
    expect(result.current.validationErrors).toEqual({ general: [], byKey: {} });
  });

  it("returns the identical normalized errors object for repeated reads of the same wire errors", () => {
    const step = makeStep({
      validation: {
        level: "UNRUNNABLE",
        isValid: false,
        errors: { general: ["Server said no"], byKey: {} },
      },
    });
    const first = renderHook(() => useStepSnapshot(step)).result.current
      .validationErrors;
    const second = renderHook(() => useStepSnapshot(step)).result.current
      .validationErrors;
    expect(second).toBe(first);
  });

  it("marks a draft step as a draft", () => {
    const { result } = renderHook(() => useStepSnapshot(makeStep({ status: "draft" })));

    expect(result.current.isDraft).toBe(true);
  });

  it("does not mark a built step as a draft", () => {
    const { result } = renderHook(() => useStepSnapshot(makeStep({ status: "built" })));

    expect(result.current.isDraft).toBe(false);
  });

  it("does not mark a ready step as a draft", () => {
    // READY is complete-but-unpushed. Treating it as a draft would tell the
    // researcher to finish a step that is already finished.
    const { result } = renderHook(() => useStepSnapshot(makeStep({ status: "ready" })));

    expect(result.current.isDraft).toBe(false);
  });

  it("a null step is not a draft", () => {
    const { result } = renderHook(() => useStepSnapshot(null));

    expect(result.current.isDraft).toBe(false);
  });

  it("carries the WDK rejection so the canvas can show it", () => {
    const { result } = renderHook(() =>
      useStepSnapshot(makeStep({ wdkPushError: "WDK rejected this step" })),
    );

    expect(result.current.wdkPushError).toBe("WDK rejected this step");
  });

  it("has no rejection for a healthy step", () => {
    const { result } = renderHook(() => useStepSnapshot(makeStep()));

    expect(result.current.wdkPushError).toBe(null);
  });

  it("a null step has no rejection", () => {
    const { result } = renderHook(() => useStepSnapshot(null));

    expect(result.current.wdkPushError).toBe(null);
  });

  it("reports every state the machine can actually be in", () => {
    for (const name of STEP_LIFECYCLE_STATE_NAMES) {
      useStrategyStore.setState({
        stepLifecycleById: { s1: seedStepMachine(name) },
      });
      const { result } = renderHook(() => useStepSnapshot(makeStep()));
      expect(result.current.lifecycleState).toBe(name);
    }
  });

  it("falls back to idle for a state value the machine never produces", () => {
    // snapshot.value is typed as XState's broad StateValue (it allows nested
    // and parallel state objects). This machine is flat, so anything that is
    // not one of its own state names is unusable and must not reach the UI.
    const foreign = { compound: "running" };
    useStrategyStore.setState({
      stepLifecycleById: {
        s1: { ...seedStepMachine("running"), value: foreign },
      },
    });
    const { result } = renderHook(() => useStepSnapshot(makeStep()));

    expect(result.current.lifecycleState).toBe("idle");
    expect(result.current.isBusy).toBe(false);
  });
});
