import { describe, expect, it } from "vitest";
import { buildStrategyTree, type TreeNode } from "./compactLayout";
import type { Step } from "@strategist/shared";

function makeStep(
  overrides: Partial<Step> & { id: string; displayName: string },
): Step {
  return { estimatedSize: null, ...overrides };
}

const search = (id: string, displayName: string) => makeStep({ id, displayName });

const combine = (
  id: string,
  operator: string,
  primaryInputStepId: string,
  secondaryInputStepId: string,
) =>
  makeStep({
    id,
    displayName: "__combine__",
    searchName: "__combine__",
    operator,
    primaryInputStepId,
    secondaryInputStepId,
  });

/** Depth-first ids, parents before children. */
function ids(nodes: TreeNode[]): string[] {
  return nodes.flatMap((n) => [n.step.id, ...ids(n.children)]);
}

function depthOf(nodes: TreeNode[], depth = 0): number {
  if (nodes.length === 0) return depth - 1;
  return Math.max(...nodes.map((n) => depthOf(n.children, depth + 1)));
}

function find(nodes: TreeNode[], id: string): TreeNode | undefined {
  for (const n of nodes) {
    if (n.step.id === id) return n;
    const hit = find(n.children, id);
    if (hit) return hit;
  }
  return undefined;
}

describe("buildStrategyTree", () => {
  it("returns nothing without a root", () => {
    expect(buildStrategyTree([], null)).toEqual([]);
    expect(buildStrategyTree([], "abc")).toEqual([]);
    expect(buildStrategyTree([search("s1", "A")], null)).toEqual([]);
  });

  it("returns a lone search as a single childless node", () => {
    const tree = buildStrategyTree([search("s1", "Search 1")], "s1");

    expect(tree).toHaveLength(1);
    expect(tree[0]!.step.displayName).toBe("Search 1");
    expect(tree[0]!.step.kind).toBe("search");
    expect(tree[0]!.children).toEqual([]);
  });

  it("puts a transform above the step it consumes", () => {
    const steps = [
      search("s1", "Search 1"),
      makeStep({ id: "t1", displayName: "Transform", primaryInputStepId: "s1" }),
    ];

    expect(ids(buildStrategyTree(steps, "t1"))).toEqual(["t1", "s1"]);
  });
});

describe("a combine is a parent of both its inputs", () => {
  const steps = [
    search("a", "A"),
    search("b", "B"),
    combine("c", "INTERSECT", "a", "b"),
  ];

  it("puts the combine on top", () => {
    expect(ids(buildStrategyTree(steps, "c"))).toEqual(["c", "a", "b"]);
  });

  it("indents both inputs equally", () => {
    const root = buildStrategyTree(steps, "c")[0];

    expect(root?.children.map((n) => n.step.id)).toEqual(["a", "b"]);
  });

  it("orders the primary input before the secondary", () => {
    const root = buildStrategyTree(steps, "c")[0];

    expect(root?.children[0]?.step.id).toBe("a");
  });

  it("names both operands", () => {
    const root = buildStrategyTree(steps, "c")[0];

    expect(root?.step.operandNames).toEqual(["A", "B"]);
  });
});

describe("a balanced strategy", () => {
  // (A u B) n (C u D)
  const steps = [
    search("a", "A"),
    search("b", "B"),
    search("c", "C"),
    search("d", "D"),
    combine("ab", "UNION", "a", "b"),
    combine("cd", "UNION", "c", "d"),
    combine("root", "INTERSECT", "ab", "cd"),
  ];

  it("reaches every step exactly once", () => {
    const all = ids(buildStrategyTree(steps, "root"));

    expect(all).toHaveLength(7);
    expect(new Set(all).size).toBe(7);
  });

  it("nests each branch under the combine that consumes it", () => {
    const tree = buildStrategyTree(steps, "root");

    expect(find(tree, "cd")?.children.map((n) => n.step.id)).toEqual(["c", "d"]);
  });

  it("keeps both branches at the same depth", () => {
    expect(depthOf(buildStrategyTree(steps, "root"))).toBe(2);
  });

  it("describes a combine operand by its own operator", () => {
    const root = buildStrategyTree(steps, "root")[0];

    expect(root?.step.operandNames).toEqual(["(A ∪ B)", "(C ∪ D)"]);
  });

  it("never emits the combine sentinel as an operand name", () => {
    const tree = buildStrategyTree(steps, "root");
    const names = ids(tree).flatMap((id) => find(tree, id)?.step.operandNames ?? []);

    expect(names).not.toContain("__combine__");
  });
});

describe("a long linear chain", () => {
  // The depth grows with the chain, so the renderer caps the visual indent.
  const steps = [
    search("s0", "S0"),
    ...Array.from({ length: 5 }, (_, i) =>
      combine(`c${i}`, "INTERSECT", i === 0 ? "s0" : `c${i - 1}`, `x${i}`),
    ),
    ...Array.from({ length: 5 }, (_, i) => search(`x${i}`, `X${i}`)),
  ];

  it("still reaches every step", () => {
    expect(new Set(ids(buildStrategyTree(steps, "c4"))).size).toBe(11);
  });

  it("nests one level per combine", () => {
    expect(depthOf(buildStrategyTree(steps, "c4"))).toBe(5);
  });
});

describe("malformed input", () => {
  it("does not hang on a cycle", () => {
    const steps = [
      combine("a", "INTERSECT", "b", "b"),
      combine("b", "INTERSECT", "a", "a"),
    ];

    expect(ids(buildStrategyTree(steps, "a")).length).toBeLessThan(10);
  });

  it("skips an input that does not exist", () => {
    const steps = [combine("c", "INTERSECT", "missing", "b"), search("b", "B")];

    expect(ids(buildStrategyTree(steps, "c"))).toEqual(["c", "b"]);
  });
});

describe("step numbers", () => {
  it("numbers steps in execution order, leaves first", () => {
    const steps = [
      search("a", "A"),
      search("b", "B"),
      combine("c", "INTERSECT", "a", "b"),
    ];
    const tree = buildStrategyTree(steps, "c");

    expect(find(tree, "a")?.step.stepNumber).toBe(1);
    expect(find(tree, "b")?.step.stepNumber).toBe(2);
    expect(find(tree, "c")?.step.stepNumber).toBe(3);
  });
});

describe("the wire step travels with each row", () => {
  // useStepSnapshot reads the count, draft status and push error off the wire
  // step. Copying fields one by one loses whichever field is forgotten, and
  // Step's optional fields mean the compiler cannot see the loss.
  const steps = [
    makeStep({ id: "a", displayName: "A", estimatedSize: 373 }),
    makeStep({ id: "b", displayName: "B", estimatedSize: 356, status: "draft" }),
    { ...combine("c", "UNION", "a", "b"), estimatedSize: 503 },
  ];

  it("carries the count of a leaf", () => {
    expect(find(buildStrategyTree(steps, "c"), "a")?.step.source.estimatedSize).toBe(
      373,
    );
  });

  it("carries the count of a combine", () => {
    expect(find(buildStrategyTree(steps, "c"), "c")?.step.source.estimatedSize).toBe(
      503,
    );
  });

  it("carries fields the view model does not model, like status", () => {
    expect(find(buildStrategyTree(steps, "c"), "b")?.step.source.status).toBe("draft");
  });

  it("carries the same object the caller passed in", () => {
    expect(find(buildStrategyTree(steps, "c"), "a")?.step.source).toBe(steps[0]);
  });
});
