import { makeStrategy } from "@/lib/types/fixtures";
import { describe, expect, test } from "vitest";
import { deserializeStrategyToGraph } from "@/features/strategy/graph/deserialize";
import type { StepPositions } from "@/features/strategy/graph/layout";

// Synthetic positions grid — each step gets a distinct (x,y) so tests can
// assert on position preservation without depending on a real layout engine.
function syntheticPositions(stepIds: string[]): StepPositions {
  const map: StepPositions = new Map();
  stepIds.forEach((id, i) => {
    map.set(id, { x: 200 + i * 300, y: 200 + i * 150 });
  });
  return map;
}

describe("deserializeStrategyToGraph", () => {
  test("returns empty graph for null/empty strategy", () => {
    expect(deserializeStrategyToGraph(null)).toEqual({ nodes: [], edges: [] });
    expect(deserializeStrategyToGraph(makeStrategy({ steps: [] }))).toEqual({
      nodes: [],
      edges: [],
    });
  });

  test("creates nodes + primary edge and sets connection affordances", () => {
    const strategy = makeStrategy({
      id: "s1",
      steps: [
        { id: "a", displayName: "A" },
        { id: "b", displayName: "B", primaryInputStepId: "a" },
      ],
    });

    const { nodes, edges } = deserializeStrategyToGraph(
      strategy,
      undefined,
      undefined,
      undefined,
      { computedPositions: syntheticPositions(["a", "b"]) },
    );
    expect(nodes.map((n) => n.id).sort()).toEqual(["a", "b"]);
    expect(edges).toHaveLength(1);
    expect(edges[0]!).toMatchObject({
      id: "a-b-primary",
      source: "a",
      target: "b",
      targetHandle: "left",
    });

    const nodeById = new Map(nodes.map((n) => [n.id, n]));
    expect(nodeById.get("a")?.data["showOutputHandle"]).toBe(false);
    expect(nodeById.get("b")?.data["showOutputHandle"]).toBe(false);
    expect(nodeById.get("b")?.data["showPrimaryInputHandle"]).toBe(false);
  });

  test("shows output handles when there are multiple roots", () => {
    const strategy = makeStrategy({
      id: "s2",
      steps: [
        { id: "a", displayName: "A" },
        { id: "b", displayName: "B" },
      ],
    });

    const { nodes } = deserializeStrategyToGraph(
      strategy,
      undefined,
      undefined,
      undefined,
      { computedPositions: syntheticPositions(["a", "b"]) },
    );
    const nodeById = new Map(nodes.map((n) => [n.id, n]));
    expect(nodeById.get("a")?.data["showOutputHandle"]).toBe(true);
    expect(nodeById.get("b")?.data["showOutputHandle"]).toBe(true);
  });

  test("combine creates primary/secondary edges with L/R labels and hides filled input handles", () => {
    const strategy = makeStrategy({
      id: "s4",
      steps: [
        { id: "left", displayName: "Left" },
        { id: "right", displayName: "Right" },
        {
          id: "comb",
          displayName: "Combine",
          primaryInputStepId: "left",
          secondaryInputStepId: "right",
          operator: "UNION",
        },
      ],
    });

    const { nodes, edges } = deserializeStrategyToGraph(
      strategy,
      undefined,
      undefined,
      undefined,
      { computedPositions: syntheticPositions(["left", "right", "comb"]) },
    );
    expect(edges).toHaveLength(2);
    expect(edges).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "left-comb-primary",
          source: "left",
          target: "comb",
          targetHandle: "left",
          label: "L (primary)",
        }),
        expect.objectContaining({
          id: "right-comb-secondary",
          source: "right",
          target: "comb",
          targetHandle: "left-secondary",
          label: "R (secondary)",
        }),
      ]),
    );

    const comb = nodes.find((n) => n.id === "comb");
    expect(comb?.data["showPrimaryInputHandle"]).toBe(false);
    expect(comb?.data["showSecondaryInputHandle"]).toBe(false);
  });

  test("combine with missing secondary input shows secondary input handle affordance", () => {
    const strategy = makeStrategy({
      id: "s5",
      steps: [
        { id: "left", displayName: "Left" },
        {
          id: "comb",
          displayName: "Combine",
          kind: "combine",
          primaryInputStepId: "left",
          operator: "UNION",
        },
      ],
    });

    const { nodes, edges } = deserializeStrategyToGraph(
      strategy,
      undefined,
      undefined,
      undefined,
      { computedPositions: syntheticPositions(["left", "comb"]) },
    );
    expect(edges).toHaveLength(1);
    const comb = nodes.find((n) => n.id === "comb");
    expect(comb?.data["showPrimaryInputHandle"]).toBe(false);
    expect(comb?.data["showSecondaryInputHandle"]).toBe(true);
  });

  test("preserves existing positions when provided; forceRelayout overrides", () => {
    const strategy = makeStrategy({
      id: "s3",
      steps: [
        { id: "a", displayName: "A" },
        { id: "b", displayName: "B" },
      ],
    });

    const existingPositions = new Map<string, { x: number; y: number }>([
      ["a", { x: 100, y: 200 }],
    ]);
    const computedPositions = syntheticPositions(["a", "b"]);

    const preserved = deserializeStrategyToGraph(
      strategy,
      undefined,
      undefined,
      undefined,
      { existingPositions, computedPositions },
    );
    const posA = preserved.nodes.find((n) => n.id === "a")?.position;
    expect(posA).toEqual({ x: 100, y: 200 });

    const relaid = deserializeStrategyToGraph(
      strategy,
      undefined,
      undefined,
      undefined,
      { existingPositions, computedPositions, forceRelayout: true },
    );
    const posA2 = relaid.nodes.find((n) => n.id === "a")?.position;
    expect(posA2).toBeTruthy();
    expect(posA2).not.toEqual({ x: 100, y: 200 });
  });

  test("passes unsavedStepIds to node data as isUnsaved flag", () => {
    const strategy = makeStrategy({
      id: "s6",
      steps: [
        { id: "a", displayName: "A" },
        { id: "b", displayName: "B" },
      ],
    });

    const unsaved = new Set(["b"]);
    const { nodes } = deserializeStrategyToGraph(
      strategy,
      undefined,
      undefined,
      unsaved,
      { computedPositions: syntheticPositions(["a", "b"]) },
    );
    const nodeById = new Map(nodes.map((n) => [n.id, n]));
    expect(nodeById.get("a")?.data["isUnsaved"]).toBe(false);
    expect(nodeById.get("b")?.data["isUnsaved"]).toBe(true);
  });

  test("skips edges for primary/secondary inputs that reference missing steps", () => {
    const strategy = makeStrategy({
      id: "s7",
      steps: [{ id: "a", displayName: "A", primaryInputStepId: "missing" }],
    });

    const { nodes, edges } = deserializeStrategyToGraph(
      strategy,
      undefined,
      undefined,
      undefined,
      { computedPositions: syntheticPositions(["a"]) },
    );
    expect(nodes).toHaveLength(1);
    expect(edges).toHaveLength(0);
  });

  test("primary edge does not get L label when step has no secondary input", () => {
    const strategy = makeStrategy({
      id: "s8",
      steps: [
        { id: "a", displayName: "A" },
        { id: "b", displayName: "B", primaryInputStepId: "a" },
      ],
    });

    const { edges } = deserializeStrategyToGraph(
      strategy,
      undefined,
      undefined,
      undefined,
      { computedPositions: syntheticPositions(["a", "b"]) },
    );
    expect(edges).toHaveLength(1);
    expect(edges[0]!.label).toBeUndefined();
  });

  test("all nodes have type='step' and correct source/target positions", () => {
    const strategy = makeStrategy({
      id: "s9",
      steps: [{ id: "a", displayName: "A" }],
    });

    const { nodes } = deserializeStrategyToGraph(
      strategy,
      undefined,
      undefined,
      undefined,
      { computedPositions: syntheticPositions(["a"]) },
    );
    expect(nodes[0]!.type).toBe("step");
    expect(nodes[0]!.sourcePosition).toBe("right");
    expect(nodes[0]!.targetPosition).toBe("left");
  });

  test("passes callback functions into node data", () => {
    const strategy = makeStrategy({
      id: "s10",
      steps: [{ id: "a", displayName: "A" }],
    });

    const onOperatorChange = () => {};
    const onOpenDetails = () => {};

    const { nodes } = deserializeStrategyToGraph(
      strategy,
      onOperatorChange,
      onOpenDetails,
      undefined,
      { computedPositions: syntheticPositions(["a"]) },
    );
    expect(nodes[0]!.data["onOperatorChange"]).toBe(onOperatorChange);
    expect(nodes[0]!.data["onOpenDetails"]).toBe(onOpenDetails);
  });

  test("transform node with missing primary input shows primary input handle", () => {
    const strategy = makeStrategy({
      id: "s11",
      steps: [{ id: "t", displayName: "T", kind: "transform" }],
    });

    const { nodes } = deserializeStrategyToGraph(
      strategy,
      undefined,
      undefined,
      undefined,
      { computedPositions: syntheticPositions(["t"]) },
    );
    const tNode = nodes.find((n) => n.id === "t");
    expect(tNode?.data["showPrimaryInputHandle"]).toBe(true);
    expect(tNode?.data["showSecondaryInputHandle"]).toBe(false);
  });

  test("secondary edge always gets R label", () => {
    const strategy = makeStrategy({
      id: "s12",
      steps: [
        { id: "a", displayName: "A" },
        { id: "b", displayName: "B" },
        {
          id: "c",
          displayName: "C",
          primaryInputStepId: "a",
          secondaryInputStepId: "b",
          operator: "UNION",
        },
      ],
    });

    const { edges } = deserializeStrategyToGraph(
      strategy,
      undefined,
      undefined,
      undefined,
      { computedPositions: syntheticPositions(["a", "b", "c"]) },
    );
    const secondaryEdge = edges.find((e) => e.id.endsWith("-secondary"));
    expect(secondaryEdge?.label).toBe("R (secondary)");
    expect(secondaryEdge?.targetHandle).toBe("left-secondary");
  });

  test("isUnsaved defaults to false when unsavedStepIds is not provided", () => {
    const strategy = makeStrategy({
      id: "s13",
      steps: [{ id: "a", displayName: "A" }],
    });

    const { nodes } = deserializeStrategyToGraph(
      strategy,
      undefined,
      undefined,
      undefined,
      { computedPositions: syntheticPositions(["a"]) },
    );
    expect(nodes[0]!.data["isUnsaved"]).toBe(false);
  });

  test("nodes without a computed position are omitted", () => {
    const strategy = makeStrategy({
      id: "s-missing",
      steps: [
        { id: "a", displayName: "A" },
        { id: "b", displayName: "B" },
      ],
    });

    const partialPositions: StepPositions = new Map([["a", { x: 100, y: 100 }]]);

    const { nodes } = deserializeStrategyToGraph(
      strategy,
      undefined,
      undefined,
      undefined,
      { computedPositions: partialPositions },
    );
    expect(nodes.map((n) => n.id)).toEqual(["a"]);
  });

  test("tags unreachable steps with data.isOrphan when rootStepId is set", () => {
    const strategy = makeStrategy({
      id: "s-orphan",
      steps: [
        { id: "a", displayName: "A" },
        { id: "b", displayName: "B" },
      ],
      rootStepId: "a",
    });

    const { nodes } = deserializeStrategyToGraph(
      strategy,
      undefined,
      undefined,
      undefined,
      { computedPositions: syntheticPositions(["a", "b"]) },
    );
    const nodeById = new Map(nodes.map((n) => [n.id, n]));
    expect(nodeById.get("a")?.data["isOrphan"]).toBe(false);
    expect(nodeById.get("b")?.data["isOrphan"]).toBe(true);
  });

  test("connected steps are not flagged as orphans", () => {
    const strategy = makeStrategy({
      id: "s-conn",
      steps: [
        { id: "a", displayName: "A" },
        { id: "b", displayName: "B", primaryInputStepId: "a" },
      ],
      rootStepId: "b",
    });

    const { nodes } = deserializeStrategyToGraph(
      strategy,
      undefined,
      undefined,
      undefined,
      { computedPositions: syntheticPositions(["a", "b"]) },
    );
    const nodeById = new Map(nodes.map((n) => [n.id, n]));
    expect(nodeById.get("a")?.data["isOrphan"]).toBe(false);
    expect(nodeById.get("b")?.data["isOrphan"]).toBe(false);
  });
});
