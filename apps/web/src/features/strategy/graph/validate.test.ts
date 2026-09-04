import { describe, expect, it } from "vitest";
import {
  findCombineRecordTypeMismatch,
  getCombineMismatchGroups,
  getRootSteps,
  resolveRecordType,
  validateStrategySteps,
} from "./validate";
import type { Step } from "@pathfinder/shared";

function step(partial: Partial<Step> & { id: string; displayName: string }): Step {
  return { isFiltered: false, ...partial };
}

describe("core/strategyGraph/validate", () => {
  it("computes root steps and rootStepId", () => {
    const steps: Step[] = [
      step({ id: "a", displayName: "A", searchName: "q1", recordType: "gene" }),
      step({
        id: "b",
        displayName: "B",
        searchName: "q2",
        recordType: "gene",
        primaryInputStepId: "a",
      }),
    ];
    expect(getRootSteps(steps).map((s) => s.id)).toEqual(["b"]);
  });

  it("reports every root when multiple roots exist", () => {
    const steps: Step[] = [
      step({ id: "a", displayName: "A", searchName: "q1", recordType: "gene" }),
      step({ id: "b", displayName: "B", searchName: "q2", recordType: "gene" }),
    ];
    expect(
      getRootSteps(steps)
        .map((s) => s.id)
        .sort(),
    ).toEqual(["a", "b"]);
  });

  it("validates missing searchName for non-combine steps", () => {
    const steps: Step[] = [step({ id: "a", displayName: "A", recordType: "gene" })];
    const errors = validateStrategySteps(steps);
    expect(
      errors.some((e) => e.code === "MISSING_SEARCH_NAME" && e.stepId === "a"),
    ).toBe(true);
  });

  it("validates invalid secondary input without primary input", () => {
    const steps: Step[] = [
      step({
        id: "c",
        displayName: "C",
        searchName: "q",
        secondaryInputStepId: "x",
        recordType: "gene",
      }),
    ];
    const errors = validateStrategySteps(steps);
    expect(errors.some((e) => e.code === "MISSING_INPUT" && e.stepId === "c")).toBe(
      true,
    );
  });

  it("validates combine invariants (operator + two inputs + colocate params)", () => {
    const steps: Step[] = [
      step({ id: "l", displayName: "L", searchName: "q1", recordType: "gene" }),
      step({ id: "r", displayName: "R", searchName: "q2", recordType: "gene" }),
      step({
        id: "c",
        displayName: "C",
        primaryInputStepId: "l",
        secondaryInputStepId: "r",
        // missing operator
        recordType: "gene",
      }),
    ];
    const errors = validateStrategySteps(steps);
    expect(errors.some((e) => e.code === "MISSING_OPERATOR" && e.stepId === "c")).toBe(
      true,
    );

    const colocate: Step = step({
      id: "co",
      displayName: "Co",
      primaryInputStepId: "l",
      secondaryInputStepId: "r",
      operator: "COLOCATE",
      recordType: "gene",
    });
    const errors2 = validateStrategySteps([steps[0]!, steps[1]!, colocate]);
    expect(errors2.some((e) => e.code === "MISSING_INPUT" && e.stepId === "co")).toBe(
      true,
    );
  });

  it("flags unknown input step ids", () => {
    const steps: Step[] = [
      step({ id: "a", displayName: "A", searchName: "q1", recordType: "gene" }),
      step({
        id: "b",
        displayName: "B",
        searchName: "q2",
        recordType: "gene",
        primaryInputStepId: "missing",
      }),
    ];
    const errors = validateStrategySteps(steps);
    expect(
      errors.some((e) => e.code === "UNKNOWN_STEP" && e.inputStepId === "missing"),
    ).toBe(true);
  });

  it("reports MULTIPLE_ROOTS as severity=info when graph has multiple outputs", () => {
    const steps: Step[] = [
      step({ id: "a", displayName: "A", searchName: "q1", recordType: "gene" }),
      step({ id: "b", displayName: "B", searchName: "q2", recordType: "gene" }),
    ];
    const errors = validateStrategySteps(steps);
    const multi = errors.find((e) => e.code === "MULTIPLE_ROOTS");
    expect(multi).toBeDefined();
    expect(multi!.severity).toBe("info");
  });

  it("structural errors carry severity=error", () => {
    const steps: Step[] = [step({ id: "a", displayName: "A", recordType: "gene" })];
    const errors = validateStrategySteps(steps);
    const missing = errors.find((e) => e.code === "MISSING_SEARCH_NAME");
    expect(missing?.severity).toBe("error");
  });

  it("detects a broken combine (operator set, secondary input removed)", () => {
    const steps: Step[] = [
      step({ id: "a", displayName: "A", searchName: "q1", recordType: "gene" }),
      step({
        id: "c",
        displayName: "Combine",
        operator: "UNION",
        primaryInputStepId: "a",
        // secondaryInputStepId removed (user deleted the node)
        recordType: "gene",
      }),
    ];
    const errors = validateStrategySteps(steps);
    expect(errors.some((e) => e.code === "MISSING_INPUT" && e.stepId === "c")).toBe(
      true,
    );
  });

  it("detects a broken combine (operator set, both inputs removed)", () => {
    const steps: Step[] = [
      step({
        id: "c",
        displayName: "Combine",
        operator: "INTERSECT",
        // both inputs removed
        recordType: "gene",
      }),
    ];
    const errors = validateStrategySteps(steps);
    expect(errors.some((e) => e.code === "MISSING_INPUT" && e.stepId === "c")).toBe(
      true,
    );
  });

  it("detects a broken combine via kind='combine' even without operator", () => {
    const steps: Step[] = [
      step({ id: "a", displayName: "A", searchName: "q1", recordType: "gene" }),
      step({
        id: "c",
        displayName: "Combine",
        kind: "combine",
        primaryInputStepId: "a",
        // secondaryInputStepId removed, operator also missing
        recordType: "gene",
      }),
    ];
    const errors = validateStrategySteps(steps);
    expect(errors.some((e) => e.code === "MISSING_INPUT" && e.stepId === "c")).toBe(
      true,
    );
    expect(errors.some((e) => e.code === "MISSING_OPERATOR" && e.stepId === "c")).toBe(
      true,
    );
  });

  it("resolves record types through transform/combine and detects mismatch", () => {
    const steps: Step[] = [
      step({ id: "left", displayName: "Left", searchName: "q1", recordType: "gene" }),
      step({
        id: "right",
        displayName: "Right",
        searchName: "q2",
        recordType: "genome",
      }),
      step({
        id: "combine",
        displayName: "Combine",
        primaryInputStepId: "left",
        secondaryInputStepId: "right",
        operator: "UNION",
      }),
    ];
    const map = new Map(steps.map((s) => [s.id, s]));
    expect(resolveRecordType("combine", map)).toBe("__mismatch__");

    const mismatch = findCombineRecordTypeMismatch(steps);
    expect(mismatch?.stepId).toBe("combine");

    const groups = getCombineMismatchGroups(steps);
    expect(groups).toHaveLength(1);
    expect(groups[0]!.ids.has("combine")).toBe(true);
  });
});
