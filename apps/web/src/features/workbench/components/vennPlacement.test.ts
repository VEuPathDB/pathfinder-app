import { describe, expect, it } from "vitest";

import { duplicateSetGroups, duplicateSetsSentence } from "./vennPlacement";

function ids(prefix: string, count: number): string[] {
  return Array.from({ length: count }, (_, i) => `${prefix}${i}`);
}

describe("duplicateSetGroups", () => {
  it("finds nothing in the disjoint selections the diagram draws today", () => {
    const sets = Array.from({ length: 5 }, (_, s) => ({
      key: `Set ${s}`,
      geneIds: ids(`s${s}_`, 20),
    }));

    expect(duplicateSetGroups(sets)).toEqual([]);
  });

  it("finds nothing when a set is only partly inside another", () => {
    const superset = ids("g", 168);
    const sets = [
      { key: "gametocyte secreted", geneIds: superset },
      { key: "candidates", geneIds: [...ids("g", 116), ...ids("h", 39)] },
    ];

    expect(duplicateSetGroups(sets)).toEqual([]);
  });

  it("groups the three lists that hold the same genes", () => {
    const shared = ids("g", 155);
    const sets = [
      { key: "gam positives", geneIds: [...ids("g", 4), "PF3D7_XXXXXXX"] },
      { key: "gametocyte secreted", geneIds: ids("g", 168) },
      { key: "gametocyte secreted candidates", geneIds: shared },
      { key: "gametocyte secreted candidates v2", geneIds: [...shared].reverse() },
      { key: "gametocyte secreted candidates v3", geneIds: shared },
    ];

    expect(duplicateSetGroups(sets)).toEqual([
      [
        "gametocyte secreted candidates",
        "gametocyte secreted candidates v2",
        "gametocyte secreted candidates v3",
      ],
    ]);
  });

  it("reports two groups when two pairs each repeat", () => {
    const sets = [
      { key: "A", geneIds: ["g1", "g2"] },
      { key: "B", geneIds: ["g2", "g1"] },
      { key: "C", geneIds: ["g3"] },
      { key: "D", geneIds: ["g3"] },
    ];

    expect(duplicateSetGroups(sets)).toEqual([
      ["A", "B"],
      ["C", "D"],
    ]);
  });

  it("ignores repeated gene ids inside one set", () => {
    const sets = [
      { key: "A", geneIds: ["g1", "g1", "g2"] },
      { key: "B", geneIds: ["g1", "g2", "g2"] },
    ];

    expect(duplicateSetGroups(sets)).toEqual([["A", "B"]]);
  });
});

describe("duplicateSetsSentence", () => {
  it("names a pair", () => {
    expect(duplicateSetsSentence(["A", "B"])).toBe(
      "A and B hold the same genes, so an overlap diagram cannot separate them.",
    );
  });

  it("names three", () => {
    expect(
      duplicateSetsSentence([
        "gametocyte secreted candidates",
        "gametocyte secreted candidates v2",
        "gametocyte secreted candidates v3",
      ]),
    ).toBe(
      "gametocyte secreted candidates, gametocyte secreted candidates v2, and " +
        "gametocyte secreted candidates v3 hold the same genes, so an overlap " +
        "diagram cannot separate them.",
    );
  });
});
