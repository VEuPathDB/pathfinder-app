import { describe, expect, test } from "vitest";
import type { Step } from "@pathfinder/shared";
import { buildIndex, findParent, walkSubtreeIds } from "./utils";

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

describe("buildIndex", () => {
  test("indexes by id and counts incoming refs", () => {
    const steps = [step("a"), step("b"), step("c", "a", "b", "combine")];
    const idx = buildIndex(steps);
    expect(idx.byId.get("a")).toBe(steps[0]);
    expect(idx.consumerOf.get("a")).toEqual({ stepId: "c", slot: "primary" });
    expect(idx.consumerOf.get("b")).toEqual({ stepId: "c", slot: "secondary" });
    expect(idx.consumerOf.has("c")).toBe(false);
  });
});

describe("findParent", () => {
  test("returns parent and slot for primary input", () => {
    const steps = [step("a"), step("b"), step("c", "a", "b", "combine")];
    expect(findParent(steps, "a")).toEqual({ parent: steps[2], slot: "primary" });
  });
  test("returns parent and slot for secondary input", () => {
    const steps = [step("a"), step("b"), step("c", "a", "b", "combine")];
    expect(findParent(steps, "b")).toEqual({ parent: steps[2], slot: "secondary" });
  });
  test("returns null for root", () => {
    const steps = [step("a"), step("b"), step("c", "a", "b", "combine")];
    expect(findParent(steps, "c")).toBe(null);
  });
  test("returns null for unknown id", () => {
    expect(findParent([step("a")], "missing")).toBe(null);
  });
});

describe("walkSubtreeIds", () => {
  test("returns ids in subtree rooted at given id", () => {
    const steps = [
      step("a"),
      step("b"),
      step("c", "a", "b", "combine"),
      step("d", "c", undefined, "transform"),
    ];
    expect(walkSubtreeIds(steps, "c").sort()).toEqual(["a", "b", "c"]);
  });
  test("includes downstream when walking from a transform parent", () => {
    const steps = [
      step("a"),
      step("b"),
      step("c", "a", "b", "combine"),
      step("d", "c", undefined, "transform"),
    ];
    expect(walkSubtreeIds(steps, "d").sort()).toEqual(["a", "b", "c", "d"]);
  });
  test("singleton for leaf", () => {
    const steps = [step("a"), step("b")];
    expect(walkSubtreeIds(steps, "a")).toEqual(["a"]);
  });
  test("empty for unknown id", () => {
    expect(walkSubtreeIds([step("a")], "missing")).toEqual([]);
  });
});
