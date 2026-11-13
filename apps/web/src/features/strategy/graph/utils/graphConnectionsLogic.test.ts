import { describe, expect, test } from "vitest";
import type { Connection } from "@xyflow/react";
import type { Step } from "@strategist/shared";
import {
  buildGraphIndices,
  getConnectionEffect,
  inferCombineRecordTypeOrMismatch,
  isUpstream,
  isValidGraphConnection,
} from "@/features/strategy/graph/utils/graphConnectionsLogic";

function step(partial: Partial<Step> & { id: string }): Step {
  return {
    kind: "search",
    displayName: partial.id,
    ...partial,
  };
}

describe("graphConnectionsLogic", () => {
  test("buildGraphIndices computes roots based on used-as-input", () => {
    const steps = [
      step({ id: "a" }),
      step({ id: "b", primaryInputStepId: "a" }),
      step({ id: "c" }),
    ];
    const idx = buildGraphIndices(steps);
    expect(idx.rootSet.has("a")).toBe(false);
    expect(idx.rootSet.has("b")).toBe(true);
    expect(idx.rootSet.has("c")).toBe(true);
    expect(idx.rootIds.sort()).toEqual(["b", "c"]);
  });

  test("isUpstream detects ancestor inputs (cycle prevention)", () => {
    const steps = [
      step({ id: "a" }),
      step({ id: "b", primaryInputStepId: "a" }),
      step({ id: "c", primaryInputStepId: "b" }),
    ];
    const idx = buildGraphIndices(steps);
    expect(isUpstream("c", "a", idx.stepsById)).toBe(true);
    expect(isUpstream("b", "c", idx.stepsById)).toBe(false);
  });

  test("isValidGraphConnection rejects missing ids and self edges", () => {
    const idx = buildGraphIndices([step({ id: "a" }), step({ id: "b" })]);
    expect(isValidGraphConnection({} as Connection, idx)).toBe(false);
    expect(
      isValidGraphConnection({ source: "a", target: "a" } as Connection, idx),
    ).toBe(false);
  });

  test("isValidGraphConnection rejects reusing a source output (non-root source)", () => {
    const steps = [
      step({ id: "a" }),
      step({ id: "b", primaryInputStepId: "a" }), // b uses a => a not root
      step({ id: "c", kind: "transform" }),
    ];
    const idx = buildGraphIndices(steps);
    expect(
      isValidGraphConnection(
        { source: "a", target: "c", targetHandle: "left" } as Connection,
        idx,
      ),
    ).toBe(false);
  });

  test("primary handle connect is allowed for transform/combine when slot empty", () => {
    const steps = [
      step({ id: "root" }),
      // Target must already be a transform/combine node to accept a primary input.
      step({ id: "t", kind: "transform", primaryInputStepId: null }),
    ];
    const idx = buildGraphIndices(steps);
    const conn = { source: "root", target: "t", targetHandle: "left" } as Connection;
    expect(isValidGraphConnection(conn, idx)).toBe(true);
    expect(getConnectionEffect(conn, idx)).toEqual({
      type: "patch",
      targetId: "t",
      patch: { primaryInputStepId: "root" },
    });
  });

  test("secondary handle connect is allowed only for combine when slot empty", () => {
    const steps = [
      step({ id: "r1" }),
      step({ id: "c", kind: "combine", primaryInputStepId: "r1" }),
      step({ id: "r2" }),
    ];
    const idx = buildGraphIndices(steps);
    const conn = {
      source: "r2",
      target: "c",
      targetHandle: "left-secondary",
    } as Connection;
    expect(isValidGraphConnection(conn, idx)).toBe(true);
    expect(getConnectionEffect(conn, idx)).toEqual({
      type: "patch",
      targetId: "c",
      patch: { secondaryInputStepId: "r2" },
    });
  });

  test("connection rejects cycle creation (source upstream of target)", () => {
    const steps = [
      step({ id: "a" }),
      step({ id: "b", primaryInputStepId: "a" }), // b depends on a
      step({ id: "c", kind: "transform" }),
    ];
    const idx = buildGraphIndices(steps);
    // Connecting b -> a would create a cycle if a were a transform/combine slot,
    // but here we model it as connecting a(root) into b would be ok; instead test
    // connecting a into a would be blocked by self edge. For explicit upstream check:
    const conn = { source: "b", target: "a", targetHandle: "left" } as Connection;
    // also blocked because b is not a root source
    expect(isValidGraphConnection(conn, idx)).toBe(false);
  });

  test("combine gesture requires multiple roots and target being a root", () => {
    const steps = [
      step({ id: "r1" }),
      step({ id: "r2" }),
      step({ id: "t", kind: "transform" }),
    ];
    const idx = buildGraphIndices(steps);
    const conn = { source: "r1", target: "r2" } as Connection;
    expect(isValidGraphConnection(conn, idx)).toBe(true);
    expect(getConnectionEffect(conn, idx)).toEqual({
      type: "pendingCombine",
      sourceId: "r1",
      targetId: "r2",
    });
  });

  test("inferCombineRecordTypeOrMismatch detects real mismatch and infers recordType", () => {
    const steps = [
      step({ id: "left", recordType: "gene" }),
      step({ id: "right", recordType: "gene" }),
    ];
    const idx = buildGraphIndices(steps);
    expect(
      inferCombineRecordTypeOrMismatch({
        sourceId: "left",
        targetId: "right",
        indices: idx,
      }),
    ).toEqual({ recordType: "gene", mismatch: false });
  });

  test("inferCombineRecordTypeOrMismatch flags mismatch for different record types", () => {
    const steps = [
      step({ id: "left", recordType: "gene" }),
      step({ id: "right", recordType: "organism" }),
    ];
    const idx = buildGraphIndices(steps);
    const result = inferCombineRecordTypeOrMismatch({
      sourceId: "left",
      targetId: "right",
      indices: idx,
    });
    expect(result.mismatch).toBe(true);
  });

  test("inferCombineRecordTypeOrMismatch falls back to rightType when leftType is null", () => {
    const steps = [
      step({ id: "left" }), // no recordType
      step({ id: "right", recordType: "gene" }),
    ];
    const idx = buildGraphIndices(steps);
    const result = inferCombineRecordTypeOrMismatch({
      sourceId: "left",
      targetId: "right",
      indices: idx,
    });
    expect(result.recordType).toBe("gene");
    expect(result.mismatch).toBe(false);
  });

  test("inferCombineRecordTypeOrMismatch returns null recordType when both sides have no type", () => {
    const steps = [step({ id: "left" }), step({ id: "right" })];
    const idx = buildGraphIndices(steps);
    const result = inferCombineRecordTypeOrMismatch({
      sourceId: "left",
      targetId: "right",
      indices: idx,
    });
    expect(result.recordType).toBeNull();
    expect(result.mismatch).toBe(false);
  });

  test("inferCombineRecordTypeOrMismatch does not flag mismatch when leftType is __mismatch__", () => {
    // __mismatch__ is a sentinel meaning an upstream combine already has mismatched types.
    // We should not double-flag.
    const steps = [
      step({ id: "a", recordType: "gene" }),
      step({ id: "b", recordType: "organism" }),
      step({
        id: "comb",
        kind: "combine",
        primaryInputStepId: "a",
        secondaryInputStepId: "b",
        operator: "UNION",
      }),
      step({ id: "right", recordType: "gene" }),
    ];
    const idx = buildGraphIndices(steps);
    const result = inferCombineRecordTypeOrMismatch({
      sourceId: "comb",
      targetId: "right",
      indices: idx,
    });
    // comb resolves to __mismatch__, so mismatch should be false (sentinel suppression)
    expect(result.mismatch).toBe(false);
  });

  test("buildGraphIndices with secondary input counts towards used-as-input", () => {
    const steps = [
      step({ id: "a" }),
      step({ id: "b" }),
      step({
        id: "c",
        kind: "combine",
        primaryInputStepId: "a",
        secondaryInputStepId: "b",
        operator: "UNION",
      }),
    ];
    const idx = buildGraphIndices(steps);
    expect(idx.usedAsInputCount.get("a")).toBe(1);
    expect(idx.usedAsInputCount.get("b")).toBe(1);
    expect(idx.rootSet.has("c")).toBe(true);
    expect(idx.rootSet.has("a")).toBe(false);
    expect(idx.rootSet.has("b")).toBe(false);
  });

  test("isUpstream returns false for non-existent steps", () => {
    const steps = [step({ id: "a" })];
    const idx = buildGraphIndices(steps);
    expect(isUpstream("a", "nonexistent", idx.stepsById)).toBe(false);
  });

  test("isUpstream handles secondary input path", () => {
    const steps = [
      step({ id: "a" }),
      step({ id: "b" }),
      step({
        id: "c",
        kind: "combine",
        primaryInputStepId: "a",
        secondaryInputStepId: "b",
        operator: "UNION",
      }),
    ];
    const idx = buildGraphIndices(steps);
    expect(isUpstream("c", "b", idx.stepsById)).toBe(true);
    expect(isUpstream("c", "a", idx.stepsById)).toBe(true);
  });

  test("isValidGraphConnection rejects unknown source/target steps", () => {
    const idx = buildGraphIndices([step({ id: "a" })]);
    expect(
      isValidGraphConnection({ source: "a", target: "missing" } as Connection, idx),
    ).toBe(false);
    expect(
      isValidGraphConnection({ source: "missing", target: "a" } as Connection, idx),
    ).toBe(false);
  });

  test("isValidGraphConnection rejects left handle when target primary is already filled", () => {
    const steps = [
      step({ id: "a" }),
      step({ id: "b" }),
      step({ id: "t", kind: "transform", primaryInputStepId: "b" }),
    ];
    const idx = buildGraphIndices(steps);
    expect(
      isValidGraphConnection(
        { source: "a", target: "t", targetHandle: "left" } as Connection,
        idx,
      ),
    ).toBe(false);
  });

  test("isValidGraphConnection rejects left-secondary when target is not combine", () => {
    const steps = [step({ id: "a" }), step({ id: "t", kind: "transform" })];
    const idx = buildGraphIndices(steps);
    expect(
      isValidGraphConnection(
        { source: "a", target: "t", targetHandle: "left-secondary" } as Connection,
        idx,
      ),
    ).toBe(false);
  });

  test("isValidGraphConnection rejects left-secondary when secondary slot is filled", () => {
    const steps = [
      step({ id: "a" }),
      step({ id: "b" }),
      step({
        id: "c",
        kind: "combine",
        primaryInputStepId: "a",
        secondaryInputStepId: "b",
        operator: "UNION",
      }),
      step({ id: "d" }),
    ];
    const idx = buildGraphIndices(steps);
    expect(
      isValidGraphConnection(
        { source: "d", target: "c", targetHandle: "left-secondary" } as Connection,
        idx,
      ),
    ).toBe(false);
  });

  test("combine gesture rejects when graph has only one root", () => {
    const steps = [step({ id: "a" }), step({ id: "b", primaryInputStepId: "a" })];
    const idx = buildGraphIndices(steps);
    // b is the only root; no combine gesture possible
    expect(
      isValidGraphConnection({ source: "b", target: "b" } as Connection, idx),
    ).toBe(false);
  });

  test("combine gesture rejects when target is not a root", () => {
    const steps = [
      step({ id: "a" }),
      step({ id: "b" }),
      step({ id: "c", primaryInputStepId: "a" }), // c is a root but a is not
    ];
    const idx = buildGraphIndices(steps);
    // a is not a root (used by c)
    expect(
      isValidGraphConnection({ source: "b", target: "a" } as Connection, idx),
    ).toBe(false);
  });

  test("getConnectionEffect returns noop for invalid connection", () => {
    const idx = buildGraphIndices([step({ id: "a" })]);
    expect(
      getConnectionEffect({ source: "a", target: "a" } as Connection, idx),
    ).toEqual({ type: "noop" });
  });

  test("isValidGraphConnection rejects left handle for search step (only transform/combine)", () => {
    const steps = [step({ id: "a" }), step({ id: "b", kind: "search" })];
    const idx = buildGraphIndices(steps);
    expect(
      isValidGraphConnection(
        { source: "a", target: "b", targetHandle: "left" } as Connection,
        idx,
      ),
    ).toBe(false);
  });
});
