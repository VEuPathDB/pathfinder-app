import { describe, expect, it } from "vitest";

import type { VocabNode } from "@/lib/utils/vocab";

import {
  ancestorsOfSelected,
  derivedExpansion,
  nodeStates,
  summarizeSelection,
  summaryLabel,
  toLeaves,
} from "./treeSelection";

const B: VocabNode = {
  value: "b",
  label: "B",
  children: [
    { value: "c", label: "C" },
    { value: "d", label: "D" },
  ],
};
const A: VocabNode = {
  value: "a",
  label: "A",
  children: [B, { value: "e", label: "E" }],
};
const tree: VocabNode[] = [A];

const multi = { multiPick: true };

function expand(t: VocabNode[], leaves: string[], opts: { multiPick: boolean }) {
  return derivedExpansion(t, nodeStates(t, new Set(leaves)), leaves, opts);
}

function summarize(t: VocabNode[], values: string[]) {
  const leaves = toLeaves(values, t);
  return summarizeSelection(t, nodeStates(t, new Set(leaves)), leaves);
}

describe("nodeStates", () => {
  it("checks a branch whose every leaf is selected", () => {
    expect(nodeStates([B], new Set(["c", "d"])).get("b")).toEqual({
      checked: true,
      leaves: ["c", "d"],
    });
  });

  it("marks a branch indeterminate when some leaves are selected", () => {
    expect(nodeStates(tree, new Set(["c", "d"])).get("a")?.checked).toBe(
      "indeterminate",
    );
  });

  it("leaves a branch unchecked when no leaf is selected", () => {
    expect(nodeStates(tree, new Set()).get("a")?.checked).toBe(false);
  });

  it("checks a selected leaf", () => {
    expect(nodeStates(tree, new Set(["e"])).get("e")).toEqual({
      checked: true,
      leaves: ["e"],
    });
  });

  it("computes every node of the tree in one pass", () => {
    const states = nodeStates(tree, new Set(["c", "d"]));
    expect([...states.entries()].map(([v, s]) => [v, s.checked])).toEqual([
      ["c", true],
      ["d", true],
      ["b", true],
      ["e", false],
      ["a", "indeterminate"],
    ]);
  });
});

describe("toLeaves", () => {
  it("expands a branch term to its leaves and keeps unknown terms", () => {
    expect(toLeaves(["b", "zzz", "e"], tree)).toEqual(["c", "d", "zzz", "e"]);
  });
});

describe("derivedExpansion", () => {
  it("expands a partial branch and keeps a full branch collapsed", () => {
    expect([...expand(tree, ["c", "d"], multi)]).toEqual(["a"]);
  });

  it("collapses a fully selected root", () => {
    expect([...expand(tree, ["c", "d", "e"], multi)]).toEqual([]);
  });

  it("expands every ancestor of a lone deep leaf", () => {
    expect([...expand(tree, ["c"], multi)].sort()).toEqual(["a", "b"]);
  });

  it("opens a single top-level branch one level when nothing is selected", () => {
    expect([...expand(tree, [], multi)]).toEqual(["a"]);
  });

  it("opens the All root and its only child when nothing is selected", () => {
    const allRoot: VocabNode[] = [{ value: "@@fake@@", label: "All", children: [A] }];
    expect([...expand(allRoot, [], multi)]).toEqual(["@@fake@@", "a"]);
  });

  it("opens only the All root when it has two children", () => {
    const allRoot: VocabNode[] = [
      { value: "@@fake@@", label: "All", children: [A, { value: "z", label: "Z" }] },
    ];
    expect([...expand(allRoot, [], multi)]).toEqual(["@@fake@@"]);
  });

  it("collapses every branch when nothing is selected and there are two roots", () => {
    const twoRoots: VocabNode[] = [B, { value: "x", label: "X", children: [A] }];
    expect([...expand(twoRoots, [], multi)]).toEqual([]);
  });

  it("ignores a value that is not in the tree", () => {
    expect([...expand(tree, ["zzz"], multi)]).toEqual(["a"]);
  });

  it("expands the path to the one pick in single-pick", () => {
    expect([...expand(tree, ["d"], { multiPick: false })].sort()).toEqual(["a", "b"]);
  });

  it("expands the path to a leaf a full branch holds in single-pick", () => {
    const lone: VocabNode[] = [
      { value: "p", label: "P", children: [{ value: "q", label: "Q" }] },
      { value: "r", label: "R" },
    ];
    expect([...expand(lone, ["q"], { multiPick: false })]).toEqual(["p"]);
  });
});

describe("ancestorsOfSelected", () => {
  it("names every branch on the path to each selected leaf", () => {
    expect([...ancestorsOfSelected(tree, ["c", "e"])].sort()).toEqual(["a", "b"]);
  });

  it("is empty for an empty selection", () => {
    expect(ancestorsOfSelected(tree, []).size).toBe(0);
  });
});

describe("summarizeSelection", () => {
  it("names the top-most full branch instead of its leaves", () => {
    expect(summarize(tree, ["c", "d"])).toEqual([
      { value: "b", label: "B", kind: "branch", leafCount: 2 },
    ]);
  });

  it("names the root alone when everything is selected", () => {
    expect(summarize(tree, ["e", "c", "d"])).toEqual([
      { value: "a", label: "A", kind: "branch", leafCount: 3 },
    ]);
  });

  it("names a lone leaf by its label", () => {
    expect(summarize(tree, ["d"])).toEqual([
      { value: "d", label: "D", kind: "leaf", leafCount: 1 },
    ]);
  });

  it("orders items in tree pre-order", () => {
    expect(summarize(tree, ["e", "c"])).toEqual([
      { value: "c", label: "C", kind: "leaf", leafCount: 1 },
      { value: "e", label: "E", kind: "leaf", leafCount: 1 },
    ]);
  });

  it("keeps a value the tree does not hold as a leaf named by its value", () => {
    expect(summarize(tree, ["zzz", "c", "d"])).toEqual([
      { value: "b", label: "B", kind: "branch", leafCount: 2 },
      { value: "zzz", label: "zzz", kind: "leaf", leafCount: 1 },
    ]);
  });

  it("is empty for an empty selection", () => {
    expect(summarize(tree, [])).toEqual([]);
  });

  it("reads a stored branch term as that branch", () => {
    expect(summarize(tree, ["b"])).toEqual([
      { value: "b", label: "B", kind: "branch", leafCount: 2 },
    ]);
  });
});

describe("summaryLabel", () => {
  it("reads a branch as its label and leaf count", () => {
    expect(summaryLabel({ value: "b", label: "B", kind: "branch", leafCount: 2 })).toBe(
      "B (all 2)",
    );
  });

  it("reads a leaf as its label", () => {
    expect(summaryLabel({ value: "e", label: "E", kind: "leaf", leafCount: 1 })).toBe(
      "E",
    );
  });
});
