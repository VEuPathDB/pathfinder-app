import { describe, expect, test } from "vitest";
import type { Step, Strategy } from "@pathfinder/shared";
import { applyOperation } from "./apply";

const strategy = (steps: Step[]): Strategy => ({
  id: "s",
  name: "T",
  siteId: "plasmodb",
  recordType: "gene",
  steps,
  rootStepId: null,
  isSaved: false,
  description: null,
  wdkStrategyId: null,
  wdkUrl: null,
  createdAt: "2026-01-01T00:00:00.000Z",
  updatedAt: "2026-01-01T00:00:00.000Z",
});

const step = (
  id: string,
  primary?: string,
  secondary?: string,
  kind: "search" | "transform" | "combine" = "search",
): Step => ({
  id,
  kind,
  displayName: id,
  primaryInputStepId: primary ?? null,
  secondaryInputStepId: secondary ?? null,
  isFiltered: false,
});

describe("applyOperation: addLeaf", () => {
  test("new-root mode appends step", () => {
    const s = strategy([step("a")]);
    const next = step("b");
    const result = applyOperation(s, {
      kind: "addLeaf",
      step: next,
      attach: { mode: "new-root" },
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    expect(result.next.steps.map((x) => x.id).sort()).toEqual(["a", "b"]);
  });

  test("into-slot mode wires target's slot to the new step", () => {
    const s = strategy([step("a", "b"), step("b")]);
    const result = applyOperation(s, {
      kind: "addLeaf",
      step: step("c"),
      attach: { mode: "into-slot", targetStepId: "a", slot: "secondary" },
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    const a = result.next.steps.find((x) => x.id === "a")!;
    expect(a.secondaryInputStepId).toBe("c");
  });

  test("rejects when target not found", () => {
    const s = strategy([step("a")]);
    const result = applyOperation(s, {
      kind: "addLeaf",
      step: step("b"),
      attach: { mode: "into-slot", targetStepId: "missing", slot: "primary" },
    });
    expect(result.kind).toBe("rejected");
  });
});

describe("applyOperation: addCombine", () => {
  test("creates combine wiring two roots", () => {
    const s = strategy([step("a"), step("b")]);
    const c = step("c", undefined, undefined, "combine");
    const result = applyOperation(s, {
      kind: "addCombine",
      step: c,
      leftId: "a",
      rightId: "b",
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    const combine = result.next.steps.find((x) => x.id === "c")!;
    expect(combine.primaryInputStepId).toBe("a");
    expect(combine.secondaryInputStepId).toBe("b");
  });

  test("rejects when leftId === rightId", () => {
    const s = strategy([step("a")]);
    const result = applyOperation(s, {
      kind: "addCombine",
      step: step("c", undefined, undefined, "combine"),
      leftId: "a",
      rightId: "a",
    });
    expect(result.kind).toBe("rejected");
  });

  test("rejects when input step missing", () => {
    const s = strategy([step("a")]);
    const result = applyOperation(s, {
      kind: "addCombine",
      step: step("c", undefined, undefined, "combine"),
      leftId: "a",
      rightId: "missing",
    });
    expect(result.kind).toBe("rejected");
  });
});

describe("applyOperation: addTransform", () => {
  test("before-consumer inserts transform between input and its consumer", () => {
    const s = strategy([step("a"), step("r", "a")]);
    const t = step("t", "a", undefined, "transform");
    const result = applyOperation(s, {
      kind: "addTransform",
      step: t,
      inputId: "a",
      mode: "before-consumer",
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    const r = result.next.steps.find((x) => x.id === "r")!;
    expect(r.primaryInputStepId).toBe("t");
    const tStep = result.next.steps.find((x) => x.id === "t")!;
    expect(tStep.primaryInputStepId).toBe("a");
  });

  test("new-root mode appends without rewiring", () => {
    const s = strategy([step("a")]);
    const t = step("t", "a", undefined, "transform");
    const result = applyOperation(s, {
      kind: "addTransform",
      step: t,
      inputId: "a",
      mode: "new-root",
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    expect(result.next.steps.map((x) => x.id).sort()).toEqual(["a", "t"]);
  });

  test("before-consumer with no consumer behaves like new-root append", () => {
    const s = strategy([step("a")]);
    const t = step("t", "a", undefined, "transform");
    const result = applyOperation(s, {
      kind: "addTransform",
      step: t,
      inputId: "a",
      mode: "before-consumer",
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    expect(result.next.steps.map((x) => x.id).sort()).toEqual(["a", "t"]);
  });
});

describe("applyOperation: deleteStep", () => {
  test("collapse-combine on nested combine: sibling reconnects to grandparent", () => {
    const steps = [
      step("A"),
      step("B"),
      step("D"),
      step("C", "A", "B", "combine"),
      step("R", "C", "D", "combine"),
    ];
    const s = strategy(steps);
    const result = applyOperation(s, {
      kind: "deleteStep",
      stepId: "A",
      resolution: "collapse-combine",
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    const ids = result.next.steps.map((x) => x.id).sort();
    expect(ids).toEqual(["B", "D", "R"]);
    const r = result.next.steps.find((x) => x.id === "R")!;
    expect(r.primaryInputStepId).toBe("B");
    expect(r.secondaryInputStepId).toBe("D");
  });

  test("collapse-combine deleting the root combine's secondary leaf drops it + the root", () => {
    const steps = [
      step("text_kinases"),
      step("go_kinase_genes"),
      step("pf_taxon"),
      step("text_or_go", "text_kinases", "go_kinase_genes", "combine"),
      step("narrowed", "text_or_go", "pf_taxon", "combine"),
    ];
    const result = applyOperation(strategy(steps), {
      kind: "deleteStep",
      stepId: "pf_taxon",
      resolution: "collapse-combine",
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    expect(result.next.steps.map((x) => x.id).sort()).toEqual([
      "go_kinase_genes",
      "text_kinases",
      "text_or_go",
    ]);
  });

  test("collapse-combine on root combine of two leaves: sibling becomes new root", () => {
    const s = strategy([step("a"), step("b"), step("c", "a", "b", "combine")]);
    const result = applyOperation(s, {
      kind: "deleteStep",
      stepId: "a",
      resolution: "collapse-combine",
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    expect(result.next.steps.map((x) => x.id).sort()).toEqual(["b"]);
  });

  test("promote-primary on root combine: drops combine + secondary subtree", () => {
    const s = strategy([step("a"), step("b"), step("c", "a", "b", "combine")]);
    const result = applyOperation(s, {
      kind: "deleteStep",
      stepId: "c",
      resolution: "promote-primary",
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    expect(result.next.steps.map((x) => x.id)).toEqual(["a"]);
  });

  test("delete-strategy on sole leaf: empties graph", () => {
    const s = strategy([step("a")]);
    const result = applyOperation(s, {
      kind: "deleteStep",
      stepId: "a",
      resolution: "delete-strategy",
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    expect(result.next.steps).toEqual([]);
  });

  test("delete-subtree on transform-input cascades transform", () => {
    const s = strategy([
      step("a"),
      step("t", "a", undefined, "transform"),
      step("r", "t"),
    ]);
    const result = applyOperation(s, {
      kind: "deleteStep",
      stepId: "a",
      resolution: "delete-subtree",
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    expect(result.next.steps.map((x) => x.id)).toEqual(["r"]);
    const r = result.next.steps.find((x) => x.id === "r")!;
    expect(r.primaryInputStepId).toBeNull();
  });

  test("rejects unknown step id", () => {
    const s = strategy([step("a")]);
    const result = applyOperation(s, {
      kind: "deleteStep",
      stepId: "missing",
      resolution: "delete-strategy",
    });
    expect(result.kind).toBe("rejected");
  });
});

describe("applyOperation: updateStepParams", () => {
  test("patches parameters", () => {
    const s = strategy([step("a")]);
    const result = applyOperation(s, {
      kind: "updateStepParams",
      stepId: "a",
      parameters: { foo: { type: "string", value: "bar" } },
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    expect(result.next.steps[0]?.parameters).toEqual({
      foo: { type: "string", value: "bar" },
    });
  });

  test("rejects unknown step id", () => {
    const s = strategy([step("a")]);
    const result = applyOperation(s, {
      kind: "updateStepParams",
      stepId: "missing",
      parameters: {},
    });
    expect(result.kind).toBe("rejected");
  });
});

describe("applyOperation: updateCombineOperator", () => {
  test("patches operator and clears colocationParams when null", () => {
    const s = strategy([step("a"), step("b"), step("c", "a", "b", "combine")]);
    const result = applyOperation(s, {
      kind: "updateCombineOperator",
      stepId: "c",
      operator: "UNION",
      colocationParams: null,
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    const c = result.next.steps.find((x) => x.id === "c")!;
    expect(c.operator).toBe("UNION");
    expect(c.colocationParams).toBeNull();
  });
});

describe("applyOperation: updateStepMeta", () => {
  test("patches displayName", () => {
    const s = strategy([step("a")]);
    const result = applyOperation(s, {
      kind: "updateStepMeta",
      stepId: "a",
      displayName: "renamed",
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    expect(result.next.steps[0]?.displayName).toBe("renamed");
  });
});

describe("applyOperation: deleteEdge", () => {
  test("detach: nulls the input slot and operator", () => {
    const s = strategy([step("a"), step("b"), step("c", "a", "b", "combine")]);
    const result = applyOperation(s, {
      kind: "deleteEdge",
      sourceId: "b",
      targetId: "c",
      slot: "secondary",
      resolution: "detach",
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    const c = result.next.steps.find((x) => x.id === "c")!;
    expect(c.secondaryInputStepId).toBeNull();
    expect(c.operator).toBeNull();
  });

  test("collapse: equivalent to deleteStep collapse-combine on the source", () => {
    const s = strategy([step("a"), step("b"), step("c", "a", "b", "combine")]);
    const result = applyOperation(s, {
      kind: "deleteEdge",
      sourceId: "a",
      targetId: "c",
      slot: "primary",
      resolution: "collapse",
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    expect(result.next.steps.map((x) => x.id).sort()).toEqual(["b"]);
  });
});

describe("applyOperation: duplicateStep", () => {
  test("the combine over the copy carries the Intersect name the api gives it", () => {
    const s = strategy([step("a")]);
    const result = applyOperation(s, {
      kind: "duplicateStep",
      sourceStepId: "a",
      duplicateStepId: "a_copy",
      combineStepId: "join",
    });
    expect(result.kind).toBe("applied");
    if (result.kind !== "applied") return;
    const join = result.next.steps.find((x) => x.id === "join");
    expect(join?.displayName).toBe("Intersect");
  });

  test("refuses a source that is not a search, as the api does", () => {
    const s = strategy([step("a"), step("b"), step("c", "a", "b", "combine")]);
    const result = applyOperation(s, {
      kind: "duplicateStep",
      sourceStepId: "c",
      duplicateStepId: "c_copy",
      combineStepId: "join",
    });
    expect(result).toEqual({
      kind: "rejected",
      reason: "Only a search step can be duplicated; step c is a combine",
    });
  });
});
