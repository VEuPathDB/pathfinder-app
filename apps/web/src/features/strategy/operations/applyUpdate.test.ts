import { makeStep, makeStrategy } from "@/lib/types/fixtures";
import { describe, expect, it } from "vitest";
import { combineOpEnum, type Step, type Strategy } from "@pathfinder/shared";

import { applyOperation } from "./apply";

// Parity tests cover topology (which steps survive, how inputs rewire); these
// pin the VALUE transformations parity doesn't — the operator flip and the
// param edit the drug-targets / workbench flows perform.

function leaf(id: string, displayName: string): Step {
  return makeStep({
    id,
    kind: "search",
    displayName,
    searchName: "GenesByText",
    recordType: "transcript",
    parameters: {
      text_expression: { type: "string", value: "kinase" },
      text_fields: { type: "multi-pick-vocabulary", values: ["product"] },
      document_type: { type: "string", value: "gene" },
    },
    operator: null,
    primaryInputStepId: null,
    secondaryInputStepId: null,
    isFiltered: false,
  });
}

function strat(): Strategy {
  const a = leaf("a", "Kinases via InterPro");
  const b = leaf("b", "Kinases via EC 2.7");
  const combine = makeStep({
    id: "c",
    kind: "combine",
    displayName: "InterPro OR EC kinases",
    searchName: "__combine__",
    recordType: "transcript",
    parameters: null,
    operator: combineOpEnum.UNION,
    primaryInputStepId: "a",
    secondaryInputStepId: "b",
    isFiltered: false,
  });
  return makeStrategy({
    id: "s",
    name: "Drug targets",
    siteId: "plasmodb",
    recordType: "transcript",
    steps: [a, b, combine],
    rootStepId: "c",
    isSaved: false,
    description: null,
    wdkStrategyId: null,
    wdkUrl: null,
    createdAt: "t",
    updatedAt: "t",
  });
}

function stepById(s: Strategy, id: string): Step {
  const found = s.steps.find((x) => x.id === id);
  if (!found) throw new Error(`no step ${id}`);
  return found;
}

describe("applyOperation — value updates", () => {
  it("flips a combine step's operator UNION → INTERSECT, leaving everything else intact", () => {
    const result = applyOperation(strat(), {
      kind: "updateCombineOperator",
      stepId: "c",
      operator: combineOpEnum.INTERSECT,
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    expect(stepById(result.next, "c").operator).toBe(combineOpEnum.INTERSECT);
    // Leaves and topology untouched.
    expect(result.next.steps.map((s) => s.id)).toEqual(["a", "b", "c"]);
    expect(stepById(result.next, "c").primaryInputStepId).toBe("a");
    expect(stepById(result.next, "c").secondaryInputStepId).toBe("b");
    expect(stepById(result.next, "a").parameters).toEqual({
      text_expression: { type: "string", value: "kinase" },
      text_fields: { type: "multi-pick-vocabulary", values: ["product"] },
      document_type: { type: "string", value: "gene" },
    });
  });

  it("merges a dirty param patch into the leaf's existing parameters", () => {
    const result = applyOperation(strat(), {
      kind: "updateStepParams",
      stepId: "a",
      parameters: { text_expression: { type: "string", value: "phosphatase" } },
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    expect(stepById(result.next, "a").parameters).toEqual({
      text_expression: { type: "string", value: "phosphatase" },
      text_fields: { type: "multi-pick-vocabulary", values: ["product"] },
      document_type: { type: "string", value: "gene" },
    });
    // Sibling leaf unchanged.
    expect(stepById(result.next, "b").parameters).toEqual({
      text_expression: { type: "string", value: "kinase" },
      text_fields: { type: "multi-pick-vocabulary", values: ["product"] },
      document_type: { type: "string", value: "gene" },
    });
  });

  it("renames a step via updateStepMeta", () => {
    const result = applyOperation(strat(), {
      kind: "updateStepMeta",
      stepId: "c",
      displayName: "InterPro AND EC kinases",
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    expect(stepById(result.next, "c").displayName).toBe("InterPro AND EC kinases");
  });

  it("flattens a null input the wire allows as no input at all", () => {
    const result = applyOperation(strat(), {
      kind: "replaceStrategy",
      root: {
        id: "a",
        searchName: "GenesByText",
        displayName: "Kinases via InterPro",
        primaryInput: null,
        secondaryInput: null,
      },
      name: "Drug targets",
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    expect(result.next.steps.map((s) => s.id)).toEqual(["a"]);
    expect(stepById(result.next, "a").kind).toBe("search");
    expect(stepById(result.next, "a").primaryInputStepId).toBe(null);
    expect(stepById(result.next, "a").secondaryInputStepId).toBe(null);
  });

  it("rejects an operator update on a non-existent step", () => {
    const result = applyOperation(strat(), {
      kind: "updateCombineOperator",
      stepId: "missing",
      operator: combineOpEnum.INTERSECT,
    });
    expect(result.kind).toBe("rejected");
    if (result.kind !== "rejected") return;
    expect(result.reason).toContain("missing");
  });
});
