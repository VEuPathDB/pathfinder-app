import { describe, expect, it } from "vitest";
import type { Search, Step } from "@pathfinder/shared";
import { computeOrthologInsert } from "@/features/strategy/graph/utils/orthologInsert";

function step(partial: Partial<Step> & { id: string }): Step {
  return {
    kind: "search",
    displayName: partial.id,
    ...partial,
  };
}

describe("computeOrthologInsert", () => {
  it("creates a transform step from selected id and patches downstream primary when insertBetween", () => {
    const steps = [
      step({ id: "a", recordType: "gene" }),
      step({ id: "b", kind: "transform", primaryInputStepId: "a" }),
    ];
    const result = computeOrthologInsert({
      selectedId: "a",
      steps,
      strategyRecordType: null,
      search: {
        name: "ortholog_search",
        displayName: "Find orthologs",
        recordType: "gene",
      } satisfies Search,
      options: { insertBetween: true },
      generateId: () => "new1",
    });

    expect(result.newStep).toMatchObject({
      id: "new1",
      kind: "transform",
      primaryInputStepId: "a",
      searchName: "ortholog_search",
      recordType: "gene",
    });
    expect(result.downstreamPatch).toEqual({
      stepId: "b",
      patch: { primaryInputStepId: "new1" },
    });
  });

  it("patches downstream secondary when downstream uses selected as secondary input", () => {
    const steps = [
      step({ id: "a", recordType: "gene" }),
      step({
        id: "c",
        kind: "combine",
        primaryInputStepId: "x",
        secondaryInputStepId: "a",
      }),
    ];
    const result = computeOrthologInsert({
      selectedId: "a",
      steps,
      strategyRecordType: null,
      search: {
        name: "ortholog_search",
        displayName: "Ortholog tool",
        recordType: "gene",
      } satisfies Search,
      options: { insertBetween: true },
      generateId: () => "new2",
    });
    expect(result.downstreamPatch).toEqual({
      stepId: "c",
      patch: { secondaryInputStepId: "new2" },
    });
  });

  it("does not patch downstream when insertBetween is false", () => {
    const steps = [
      step({ id: "a", recordType: "gene" }),
      step({ id: "b", kind: "transform", primaryInputStepId: "a" }),
    ];
    const result = computeOrthologInsert({
      selectedId: "a",
      steps,
      strategyRecordType: null,
      search: {
        name: "ortholog_search",
        displayName: "",
        recordType: "gene",
      } satisfies Search,
      options: { insertBetween: false },
      generateId: () => "new3",
    });
    expect(result.downstreamPatch).toEqual(undefined);
  });
});
