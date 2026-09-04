import { describe, expect, it } from "vitest";
import { inferStepKind } from "./kind";

describe("inferStepKind", () => {
  // ── Explicit kind takes priority ──────────────────────────

  it("returns the explicit kind when provided", () => {
    expect(inferStepKind({ kind: "search" })).toBe("search");
    expect(inferStepKind({ kind: "transform" })).toBe("transform");
    expect(inferStepKind({ kind: "combine" })).toBe("combine");
  });

  it("returns explicit kind even if inputs suggest otherwise", () => {
    expect(
      inferStepKind({
        kind: "search",
        primaryInputStepId: "a",
        secondaryInputStepId: "b",
      }),
    ).toBe("search");
  });

  // ── Combine inference ─────────────────────────────────────

  it('infers "combine" when both input step IDs are present', () => {
    expect(
      inferStepKind({
        primaryInputStepId: "a",
        secondaryInputStepId: "b",
      }),
    ).toBe("combine");
  });

  it('infers "combine" when only operator is present (no inputs)', () => {
    expect(inferStepKind({ operator: "INTERSECT" })).toBe("combine");
  });

  it('infers "combine" when operator is present with only primary input', () => {
    expect(
      inferStepKind({
        operator: "UNION",
        primaryInputStepId: "a",
      }),
    ).toBe("combine");
  });

  it('infers "combine" when operator is present with both inputs', () => {
    expect(
      inferStepKind({
        operator: "MINUS",
        primaryInputStepId: "a",
        secondaryInputStepId: "b",
      }),
    ).toBe("combine");
  });

  // ── Transform inference ───────────────────────────────────

  it('infers "transform" when only primaryInputStepId is present', () => {
    expect(inferStepKind({ primaryInputStepId: "a" })).toBe("transform");
  });

  // ── Search inference (default) ────────────────────────────

  it('infers "search" when no kind, no inputs, no operator', () => {
    expect(inferStepKind({})).toBe("search");
  });

  it('infers "search" when only secondaryInputStepId is present (unusual)', () => {
    // This is an edge case: secondary without primary (and no operator)
    // should still fall through to "search" since the primary check is first
    expect(inferStepKind({ secondaryInputStepId: "b" })).toBe("search");
  });

  // ── Undefined fields are treated as absent ────────────────

  it("treats undefined kind as absent", () => {
    expect(inferStepKind({})).toBe("search");
  });

  it("treats null inputs as absent", () => {
    expect(
      inferStepKind({
        primaryInputStepId: null,
        secondaryInputStepId: null,
      }),
    ).toBe("search");
  });

  it("treats null operator as absent", () => {
    expect(inferStepKind({ operator: null })).toBe("search");
  });
});
