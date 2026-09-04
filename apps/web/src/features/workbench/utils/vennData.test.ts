import { describe, it, expect } from "vitest";
import { computeVennData, computeExclusiveRegions, logScaleVennData } from "./vennData";

describe("computeVennData", () => {
  it("computes 2-set Venn data with correct inclusive counts", () => {
    const sets = [
      { key: "A", geneIds: ["g1", "g2", "g3"] },
      { key: "B", geneIds: ["g2", "g3", "g4", "g5"] },
    ];
    const data = computeVennData(sets);
    expect(data).toContainEqual({ key: ["A"], data: 3 });
    expect(data).toContainEqual({ key: ["B"], data: 4 });
    expect(data).toContainEqual({ key: ["A", "B"], data: 2 });
  });

  it("computes 3-set Venn data with all intersections", () => {
    const sets = [
      { key: "X", geneIds: ["g1", "g2", "g3", "g4"] },
      { key: "Y", geneIds: ["g3", "g4", "g5"] },
      { key: "Z", geneIds: ["g4", "g5", "g6"] },
    ];
    const data = computeVennData(sets);
    expect(data).toContainEqual({ key: ["X"], data: 4 });
    expect(data).toContainEqual({ key: ["Y"], data: 3 });
    expect(data).toContainEqual({ key: ["Z"], data: 3 });
    expect(data).toContainEqual({ key: ["X", "Y"], data: 2 });
    expect(data).toContainEqual({ key: ["X", "Z"], data: 1 });
    expect(data).toContainEqual({ key: ["Y", "Z"], data: 2 });
    expect(data).toContainEqual({ key: ["X", "Y", "Z"], data: 1 });
  });

  it("handles empty sets", () => {
    const sets = [
      { key: "A", geneIds: [] as string[] },
      { key: "B", geneIds: ["g1"] },
    ];
    const data = computeVennData(sets);
    expect(data).toContainEqual({ key: ["A"], data: 0 });
    expect(data).toContainEqual({ key: ["B"], data: 1 });
    expect(data).toContainEqual({ key: ["A", "B"], data: 0 });
  });

  it("handles fully overlapping sets", () => {
    const sets = [
      { key: "A", geneIds: ["g1", "g2"] },
      { key: "B", geneIds: ["g1", "g2"] },
    ];
    const data = computeVennData(sets);
    expect(data).toContainEqual({ key: ["A"], data: 2 });
    expect(data).toContainEqual({ key: ["B"], data: 2 });
    expect(data).toContainEqual({ key: ["A", "B"], data: 2 });
  });

  it("handles single set", () => {
    const sets = [{ key: "Solo", geneIds: ["g1", "g2", "g3"] }];
    const data = computeVennData(sets);
    expect(data).toEqual([{ key: ["Solo"], data: 3 }]);
  });
});

describe("logScaleVennData", () => {
  it("compresses extreme size ratios so small sets remain visible", () => {
    const data = [
      { key: ["Big"], data: 100_000 },
      { key: ["Small"], data: 1 },
      { key: ["Big", "Small"], data: 1 },
    ];
    const scaled = logScaleVennData(data);
    const bigSize = scaled.find((d) => d.key.length === 1 && d.key[0] === "Big")!.data;
    const smallSize = scaled.find(
      (d) => d.key.length === 1 && d.key[0] === "Small",
    )!.data;
    // Raw ratio is 100,000:1. After log scaling, ratio should be < 20:1
    expect(bigSize / smallSize).toBeLessThan(20);
    // Both must be > 0
    expect(bigSize).toBeGreaterThan(0);
    expect(smallSize).toBeGreaterThan(0);
  });

  it("preserves zero counts as zero", () => {
    const data = [
      { key: ["A"], data: 50 },
      { key: ["B"], data: 0 },
      { key: ["A", "B"], data: 0 },
    ];
    const scaled = logScaleVennData(data);
    expect(scaled.find((d) => d.key[0] === "B" && d.key.length === 1)!.data).toBe(0);
    expect(scaled.find((d) => d.key.length === 2)!.data).toBe(0);
  });

  it("preserves relative ordering", () => {
    const data = [
      { key: ["A"], data: 10_000 },
      { key: ["B"], data: 500 },
      { key: ["C"], data: 10 },
      { key: ["A", "B"], data: 200 },
      { key: ["B", "C"], data: 5 },
      { key: ["A", "C"], data: 3 },
      { key: ["A", "B", "C"], data: 1 },
    ];
    const scaled = logScaleVennData(data);
    const get = (k: string[]) =>
      scaled.find((d) => d.key.join(",") === k.join(","))!.data;
    expect(get(["A"])).toBeGreaterThan(get(["B"]));
    expect(get(["B"])).toBeGreaterThan(get(["C"]));
    expect(get(["A", "B"])).toBeGreaterThan(get(["B", "C"]));
  });

  it("returns same keys as input", () => {
    const data = [
      { key: ["X"], data: 999 },
      { key: ["Y"], data: 1 },
      { key: ["X", "Y"], data: 1 },
    ];
    const scaled = logScaleVennData(data);
    expect(scaled.map((d) => d.key)).toEqual(data.map((d) => d.key));
  });
});

describe("computeExclusiveRegions", () => {
  it("returns exclusive gene IDs for each region of a 2-set Venn", () => {
    const sets = [
      { key: "A", geneIds: ["g1", "g2", "g3"] },
      { key: "B", geneIds: ["g2", "g3", "g4", "g5"] },
    ];
    const regions = computeExclusiveRegions(sets);
    expect(regions.get("A")?.sort()).toEqual(["g1"]);
    expect(regions.get("B")?.sort()).toEqual(["g4", "g5"]);
    expect(regions.get("A,B")?.sort()).toEqual(["g2", "g3"]);
  });

  it("returns exclusive regions for 3 sets", () => {
    const sets = [
      { key: "X", geneIds: ["g1", "g2", "g3", "g4"] },
      { key: "Y", geneIds: ["g3", "g4", "g5"] },
      { key: "Z", geneIds: ["g4", "g5", "g6"] },
    ];
    const regions = computeExclusiveRegions(sets);
    expect(regions.get("X")?.sort()).toEqual(["g1", "g2"]);
    expect(regions.get("Y") ?? []).toEqual([]);
    expect(regions.get("Z")).toEqual(["g6"]);
    expect(regions.get("X,Y")).toEqual(["g3"]);
    expect(regions.get("Y,Z")).toEqual(["g5"]);
    expect(regions.get("X,Z") ?? []).toEqual([]);
    expect(regions.get("X,Y,Z")).toEqual(["g4"]);
  });

  it("handles disjoint sets", () => {
    const sets = [
      { key: "A", geneIds: ["g1", "g2"] },
      { key: "B", geneIds: ["g3", "g4"] },
    ];
    const regions = computeExclusiveRegions(sets);
    expect(regions.get("A")?.sort()).toEqual(["g1", "g2"]);
    expect(regions.get("B")?.sort()).toEqual(["g3", "g4"]);
    expect(regions.has("A,B")).toBe(false);
  });
});
