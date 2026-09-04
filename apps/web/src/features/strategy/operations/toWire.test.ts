import { describe, expect, it } from "vitest";
import type { Step } from "@pathfinder/shared";
import { toWireOperation } from "./toWire";
import type { GraphOperation } from "@/lib/types/graphOperation";

/**
 * The canvas reducer works on flat `Step`s so it can splice `Strategy.steps`;
 * the API takes nested `StrategyStepNode`s. That gap used to be bridged by an
 * `as` cast at the mutation boundary, which let the frontend send a `deleteEdge`
 * operation the backend's union did not contain - a guaranteed 422 on a gesture
 * that had already appeared to succeed.
 *
 * These tests pin the conversion. The real guard is the compiler: `toWire`
 * declares the generated `ApplyOperationRequest["op"]` as its return type, so
 * any operation the backend does not accept fails the build instead of the request.
 */

function step(overrides: Partial<Step> = {}): Step {
  return {
    id: "s1",
    searchName: "GenesByMolecularWeight",
    displayName: "Molecular weight",
    recordType: "transcript",
    parameters: {},
    primaryInputStepId: null,
    secondaryInputStepId: null,
    operator: null,
    isFiltered: false,
    ...overrides,
  };
}

describe("toWireOperation", () => {
  it("sends deleteEdge with both endpoints", () => {
    const op: GraphOperation = {
      kind: "deleteEdge",
      sourceId: "a",
      targetId: "b",
      slot: "secondary",
      resolution: "detach",
    };

    expect(toWireOperation(op)).toEqual({
      kind: "deleteEdge",
      sourceId: "a",
      targetId: "b",
      slot: "secondary",
      resolution: "detach",
    });
  });

  it("projects a flat step onto the nested node shape", () => {
    const op: GraphOperation = {
      kind: "addLeaf",
      step: step({ id: "new1", displayName: "Kinases" }),
      attach: { mode: "new-root" },
    };

    expect(toWireOperation(op)).toEqual({
      kind: "addLeaf",
      step: {
        id: "new1",
        searchName: "GenesByMolecularWeight",
        displayName: "Kinases",
        parameters: {},
      },
      attach: { mode: "new-root" },
    });
  });

  it("drops canvas-only fields the API does not model", () => {
    const op: GraphOperation = {
      kind: "addLeaf",
      step: step({ status: "draft", isFiltered: true, recordType: "gene" }),
      attach: { mode: "new-root" },
    };

    const wire = toWireOperation(op);

    expect(wire).not.toHaveProperty("step.status");
    expect(wire).not.toHaveProperty("step.isFiltered");
    expect(wire).not.toHaveProperty("step.recordType");
  });

  it("does not send the input ids as node fields on an added step", () => {
    // Wiring travels in `leftId`/`rightId`, not inside the node. Sending
    // `primaryInputStepId` would be silently dropped by Pydantic's
    // extra="ignore" rather than rejected.
    const op: GraphOperation = {
      kind: "addCombine",
      step: step({ id: "c1", primaryInputStepId: "a", secondaryInputStepId: "b" }),
      leftId: "a",
      rightId: "b",
    };

    const wire = toWireOperation(op);

    expect(wire).not.toHaveProperty("step.primaryInputStepId");
    expect(wire).toMatchObject({ kind: "addCombine", leftId: "a", rightId: "b" });
  });

  it("carries the combine operator and colocation params", () => {
    const op: GraphOperation = {
      kind: "updateCombineOperator",
      stepId: "c1",
      operator: "COLOCATE",
      colocationParams: { operation: "overlaps", strand: "same strand" },
    };

    expect(toWireOperation(op)).toEqual({
      kind: "updateCombineOperator",
      stepId: "c1",
      operator: "COLOCATE",
      colocationParams: { operation: "overlaps", strand: "same strand" },
    });
  });

  it("preserves the attach slot for a leaf added into a combine input", () => {
    const op: GraphOperation = {
      kind: "addLeaf",
      step: step({ id: "new1" }),
      attach: { mode: "into-slot", targetStepId: "c1", slot: "secondary" },
    };

    expect(toWireOperation(op)).toMatchObject({
      attach: { mode: "into-slot", targetStepId: "c1", slot: "secondary" },
    });
  });

  it("passes updateStepParams through untouched", () => {
    const op: GraphOperation = {
      kind: "updateStepParams",
      stepId: "s1",
      parameters: {
        organism: { type: "multi-pick-vocabulary", values: ["P. falciparum 3D7"] },
      },
    };

    expect(toWireOperation(op)).toEqual({
      kind: "updateStepParams",
      stepId: "s1",
      parameters: {
        organism: { type: "multi-pick-vocabulary", values: ["P. falciparum 3D7"] },
      },
    });
  });

  it("keeps an explicit null description on updateStrategyMeta", () => {
    // `undefined` would be omitted from the JSON body and read as "no change";
    // clearing a description has to survive the trip.
    const op: GraphOperation = {
      kind: "updateStrategyMeta",
      name: "Renamed",
      description: null,
    };

    expect(toWireOperation(op)).toEqual({
      kind: "updateStrategyMeta",
      name: "Renamed",
      description: null,
    });
  });
});
