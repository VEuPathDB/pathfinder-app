import { describe, expect, it } from "vitest";
import { serializeStrategyAst } from "./serialize";
import type { Step, Strategy } from "@pathfinder/shared";

/** Minimal Step with required boolean fields defaulted. */
function step(partial: Partial<Step> & { id: string; displayName: string }): Step {
  return { isFiltered: false, ...partial };
}

describe("core/strategyGraph/serialize", () => {
  it("returns null when graph has multiple roots (multiple outputs)", () => {
    const stepsById: Record<string, Step> = {
      a: step({ id: "a", displayName: "A", searchName: "q1", recordType: "gene" }),
      b: step({ id: "b", displayName: "B", searchName: "q2", recordType: "gene" }),
    };
    const res = serializeStrategyAst(stepsById, {
      id: "s",
      name: "S",
      siteId: "plasmodb",
      recordType: "gene",
      steps: Object.values(stepsById),
      rootStepId: null,
      isSaved: false,
      createdAt: "t",
      updatedAt: "t",
    });
    expect(res).toEqual(null);
  });

  it("serializes a linear plan and sanitizes @@fake@@ parameters", () => {
    const stepsById: Record<string, Step> = {
      a: step({
        id: "a",
        displayName: "A",
        searchName: "q1",
        recordType: "gene",
        parameters: {
          ok: { type: "number", value: 1 },
          fake: { type: "single-pick-vocabulary", value: "@@fake@@" },
          arr: { type: "multi-pick-vocabulary", values: ["x", "@@fake@@"] },
        },
      }),
      b: step({
        id: "b",
        displayName: "B",
        searchName: "q2",
        recordType: "gene",
        primaryInputStepId: "a",
        parameters: { ok: { type: "string", value: "true" } },
      }),
    };

    const strategy: Strategy = {
      id: "s1",
      name: "My Strategy",
      description: "desc",
      siteId: "plasmodb",
      recordType: "gene",
      steps: Object.values(stepsById),
      rootStepId: "b",
      isSaved: false,
      createdAt: "t",
      updatedAt: "t",
    };

    const res = serializeStrategyAst(stepsById, strategy);
    expect(res?.plan.root.id).toBe("b");
    expect(res?.plan.root.primaryInput?.id).toBe("a");
    // Any params containing the UI-only @@fake@@ sentinel are removed.
    expect(res?.plan.root.primaryInput?.parameters).toEqual({
      ok: { type: "number", value: 1 },
    });
    expect(res?.plan.root.primaryInput?.parameters?.["fake"]).toBeUndefined();
    expect(res?.plan.root.primaryInput?.parameters?.["arr"]).toBeUndefined();
    expect(res?.plan.name).toBe("My Strategy");
    expect(res?.plan.description).toBe("desc");
  });

  it("uses rootStepId when set, emits orphans for unreachable steps", () => {
    const stepsById: Record<string, Step> = {
      a: step({ id: "a", displayName: "A", searchName: "q1", recordType: "gene" }),
      b: step({ id: "b", displayName: "B", searchName: "q2", recordType: "gene" }),
    };
    const strategy: Strategy = {
      id: "s",
      name: "S",
      siteId: "plasmodb",
      recordType: "gene",
      steps: Object.values(stepsById),
      rootStepId: "a",
      isSaved: false,
      createdAt: "t",
      updatedAt: "t",
    };
    const res = serializeStrategyAst(stepsById, strategy);
    expect(res).not.toBeNull();
    expect(res?.plan.root.id).toBe("a");
    expect(res?.orphanIds).toEqual(["b"]);
  });

  it("falls through to single-root selection when rootStepId is null and exactly one root exists", () => {
    const stepsById: Record<string, Step> = {
      a: step({ id: "a", displayName: "A", searchName: "q1", recordType: "gene" }),
    };
    const strategy: Strategy = {
      id: "s",
      name: "S",
      siteId: "plasmodb",
      recordType: "gene",
      steps: Object.values(stepsById),
      rootStepId: null,
      isSaved: false,
      createdAt: "t",
      updatedAt: "t",
    };
    const res = serializeStrategyAst(stepsById, strategy);
    expect(res?.plan.root.id).toBe("a");
    expect(res?.orphanIds).toEqual([]);
  });

  it("orphanIds is [] when graph is fully connected from rootStepId", () => {
    const stepsById: Record<string, Step> = {
      a: step({ id: "a", displayName: "A", searchName: "q1", recordType: "gene" }),
      b: step({
        id: "b",
        displayName: "B",
        searchName: "q2",
        recordType: "gene",
        primaryInputStepId: "a",
      }),
    };
    const strategy: Strategy = {
      id: "s",
      name: "S",
      siteId: "plasmodb",
      recordType: "gene",
      steps: Object.values(stepsById),
      rootStepId: "b",
      isSaved: false,
      createdAt: "t",
      updatedAt: "t",
    };
    const res = serializeStrategyAst(stepsById, strategy);
    expect(res?.orphanIds).toEqual([]);
  });

  it("serializes combine nodes with __combine__ searchName and requires operator", () => {
    const stepsById: Record<string, Step> = {
      l: step({ id: "l", displayName: "L", searchName: "q1", recordType: "gene" }),
      r: step({ id: "r", displayName: "R", searchName: "q2", recordType: "gene" }),
      c: step({
        id: "c",
        displayName: "C",
        primaryInputStepId: "l",
        secondaryInputStepId: "r",
        operator: "UNION",
        recordType: "gene",
      }),
    };

    const strategy: Strategy = {
      id: "s1",
      name: "S",
      siteId: "plasmodb",
      recordType: "gene",
      steps: Object.values(stepsById),
      rootStepId: "c",
      isSaved: false,
      createdAt: "t",
      updatedAt: "t",
    };

    const res = serializeStrategyAst(stepsById, strategy);
    expect(res?.plan.root.searchName).toBe("__combine__");
    expect(res?.plan.root.operator).toBe("UNION");

    const stepC = stepsById["c"]!;
    const broken = { ...stepsById, c: { ...stepC, operator: null } };
    const res2 = serializeStrategyAst(broken, strategy);
    expect(res2).toBeNull();
  });
});
