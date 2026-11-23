// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { colocationSchema } from "./colocationSchema";

describe("colocationSchema", () => {
  const validParams = {
    operation: "overlaps",
    strand: "either strand",
    output: "a",
    regionA: "exact",
    beginA: "start",
    beginDirectionA: "+",
    beginOffsetA: 0,
    endA: "stop",
    endDirectionA: "+",
    endOffsetA: 0,
    regionB: "exact",
    beginB: "start",
    beginDirectionB: "+",
    beginOffsetB: 0,
    endB: "stop",
    endDirectionB: "+",
    endOffsetB: 0,
  };

  it("accepts valid colocation params", () => {
    expect(colocationSchema.safeParse(validParams).success).toBe(true);
  });

  it("rejects negative offsets", () => {
    expect(
      colocationSchema.safeParse({ ...validParams, beginOffsetA: -1 }).success,
    ).toBe(false);
  });

  it("accepts zero offsets", () => {
    expect(
      colocationSchema.safeParse({ ...validParams, beginOffsetA: 0 }).success,
    ).toBe(true);
  });

  it("accepts positive offsets", () => {
    expect(
      colocationSchema.safeParse({ ...validParams, endOffsetB: 5000 }).success,
    ).toBe(true);
  });

  it("accepts all valid operations", () => {
    for (const op of ["overlaps", "contains", "is contained in"]) {
      expect(
        colocationSchema.safeParse({ ...validParams, operation: op }).success,
      ).toBe(true);
    }
  });

  it("accepts all valid strands", () => {
    for (const s of ["either strand", "same strand", "opposite strand"]) {
      expect(colocationSchema.safeParse({ ...validParams, strand: s }).success).toBe(
        true,
      );
    }
  });

  it("accepts both directions", () => {
    expect(
      colocationSchema.safeParse({ ...validParams, beginDirectionA: "+" }).success,
    ).toBe(true);
    expect(
      colocationSchema.safeParse({ ...validParams, beginDirectionA: "-" }).success,
    ).toBe(true);
  });
});
