import { describe, expect, it } from "vitest";
import type { Step, Strategy } from "@pathfinder/shared";
import { stepsById } from "./selectors";

// The WeakMap cache keys on the steps ARRAY identity: the same array must not
// rebuild the map, or every memoized consumer re-renders.

function step(id: string): Step {
  return { id, searchName: "GenesByTaxon", isFiltered: false };
}

function strategy(steps: Step[]): Strategy {
  return {
    id: "s",
    name: "T",
    siteId: "plasmodb",
    isSaved: false,
    recordType: "gene",
    steps,
    createdAt: "2026-01-01T00:00:00.000Z",
    updatedAt: "2026-01-01T00:00:00.000Z",
  };
}

describe("state/strategy/selectors - stepsById", () => {
  it("indexes steps by id", () => {
    const result = stepsById(strategy([step("a"), step("b")]));

    expect(Object.keys(result).sort()).toEqual(["a", "b"]);
    expect(result["a"]?.id).toBe("a");
  });

  it("returns the same object for the same steps array", () => {
    const s = strategy([step("a")]);

    expect(stepsById(s)).toBe(stepsById(s));
  });

  it("rebuilds when the steps array identity changes", () => {
    const first = stepsById(strategy([step("a")]));
    const second = stepsById(strategy([step("a")]));

    expect(second).not.toBe(first);
    expect(second).toEqual(first);
  });

  it("returns the shared empty map for a strategy with no steps", () => {
    expect(stepsById(strategy([]))).toBe(stepsById(strategy([])));
    expect(stepsById(strategy([]))).toEqual({});
  });

  it("returns the shared empty map for null and undefined", () => {
    expect(stepsById(null)).toEqual({});
    expect(stepsById(undefined)).toEqual({});
    expect(stepsById(null)).toBe(stepsById(undefined));
  });

  it("the empty map is frozen so a caller cannot poison the shared value", () => {
    const empty = stepsById(null);

    expect(Object.isFrozen(empty)).toBe(true);
  });

  it("a later step with a duplicate id wins", () => {
    const first = step("a");
    const second = { ...step("a"), searchName: "GenesByText" };

    const result = stepsById(strategy([first, second]));

    expect(result["a"]?.searchName).toBe("GenesByText");
  });

  it("keeps every step when ids are distinct", () => {
    const result = stepsById(strategy([step("a"), step("b"), step("c")]));

    expect(Object.keys(result)).toHaveLength(3);
  });
});
