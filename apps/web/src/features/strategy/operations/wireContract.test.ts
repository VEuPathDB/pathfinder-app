import { describe, expect, it } from "vitest";
import type { Step } from "@strategist/shared";
import { deleteResolutionEnum } from "@strategist/shared/generated/types/DeleteResolution";
import { deleteEdgeResolutionEnum } from "@strategist/shared/generated/types/DeleteEdgeResolution";
import { computeDeleteChoices } from "./deleteResolutions";

/**
 * The frontend used to declare its own operation vocabulary and cast it onto
 * the request type. Two values in that vocabulary had no backend counterpart -
 * `deleteEdge` and the `orphan-sibling` delete resolution - so both produced a
 * 422 on a gesture the canvas had already shown as successful.
 *
 * `toWireOperation` closes the hole at the type level for operation kinds.
 * Resolutions are strings inside an operation, so the compiler only checks
 * them against the generated enum if something asserts the relationship;
 * that is this file's job.
 */

function step(id: string, primary?: string, secondary?: string): Step {
  return {
    id,
    searchName: "GenesByText",
    displayName: id,
    recordType: "transcript",
    parameters: {},
    primaryInputStepId: primary ?? null,
    secondaryInputStepId: secondary ?? null,
    operator: secondary != null ? "INTERSECT" : null,
    isFiltered: false,
  };
}

const BACKEND_RESOLUTIONS = new Set(Object.values(deleteResolutionEnum));

describe("delete resolutions stay inside the backend enum", () => {
  const cases: { name: string; steps: Step[]; target: string }[] = [
    { name: "only step", steps: [step("a")], target: "a" },
    {
      name: "leaf under a combine",
      steps: [step("a"), step("b"), step("c", "a", "b")],
      target: "b",
    },
    {
      name: "the combine itself",
      steps: [step("a"), step("b"), step("c", "a", "b")],
      target: "c",
    },
    {
      name: "leaf under a transform",
      steps: [step("a"), step("t", "a")],
      target: "a",
    },
    {
      name: "nested combine under a combine",
      steps: [
        step("a"),
        step("b"),
        step("c", "a", "b"),
        step("d"),
        step("e", "c", "d"),
      ],
      target: "c",
    },
  ];

  for (const { name, steps, target } of cases) {
    it(`offers only backend-known resolutions for ${name}`, () => {
      const choices = computeDeleteChoices(steps, target);

      expect(choices.length).toBeGreaterThan(0);
      for (const choice of choices) {
        expect(BACKEND_RESOLUTIONS).toContain(choice.resolution);
      }
    });
  }

  it("still offers exactly one default per dialog", () => {
    for (const { steps, target } of cases) {
      const defaults = computeDeleteChoices(steps, target).filter((c) => c.isDefault);
      expect(defaults).toHaveLength(1);
    }
  });

  it("pins the resolutions the backend implements", () => {
    // A new member here is a deliberate contract change, not an accident.
    expect(Object.values(deleteResolutionEnum).sort()).toEqual([
      "collapse-combine",
      "delete-strategy",
      "delete-subtree",
      "orphan-sibling",
      "promote-primary",
    ]);
  });

  it("pins the edge resolutions the backend implements", () => {
    expect(Object.values(deleteEdgeResolutionEnum).sort()).toEqual([
      "collapse",
      "detach",
    ]);
  });

  it("offers orphaning again now that detached components persist", () => {
    // This was pulled while StrategyAst could hold only one root: orphaning a
    // combine produced a second component with nowhere to live, so the delete
    // pushed to WDK and was then silently not written down.
    // StrategyAst.detached_roots is that component's home.
    const steps = [step("a"), step("b"), step("c", "a", "b")];

    const offered = computeDeleteChoices(steps, "b").map((c) => c.resolution);

    expect(offered).toContain("orphan-sibling");
  });
});

describe("useApplyOperation sends what the canvas shows", () => {
  it("keeps the deleteEdge resolutions the canvas can produce", () => {
    // The edge control offers detach; collapse is reachable from the
    // delete dialog on the combine itself.
    expect(Object.values(deleteEdgeResolutionEnum)).toContain("detach");
  });

  it("does not strand a strategy with no steps", () => {
    const choices = computeDeleteChoices([step("a")], "a");
    expect(choices.map((c) => c.resolution)).toContain("delete-strategy");
  });
});
