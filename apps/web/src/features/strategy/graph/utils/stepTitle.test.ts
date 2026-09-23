import { describe, expect, test } from "vitest";
import type { Step } from "@pathfinder/shared";
import { operatorName, stepSubtitle, stepTitle } from "./stepTitle";

import fixture from "../../../../../../../packages/spec/operations_parity.json";

const WDK_DEFAULT = "boolean_question_TranscriptRecordClasses_TranscriptRecordClass";

function combineStep(displayName: string, searchName = "__combine__"): Step {
  return {
    id: "step_join",
    kind: "combine",
    displayName,
    searchName,
    primaryInputStepId: "a",
    secondaryInputStepId: "b",
    operator: "UNION",
    isFiltered: false,
  };
}

describe("operatorName", () => {
  test("names every operator the way the api names its combine", () => {
    const labels = Object.fromEntries(
      Object.keys(fixture.combine_labels).map((op) => [op, operatorName(op)]),
    );

    expect(labels).toEqual(fixture.combine_labels);
  });
});

describe("stepTitle", () => {
  test.each([
    ["", "__combine__"],
    [WDK_DEFAULT, WDK_DEFAULT],
    ["Intersect", "__combine__"],
  ])("a combine named %j under %j shows its operator", (name, search) => {
    expect(stepTitle(combineStep(name, search), "combine")).toBe("Union");
  });

  test("a combine a researcher named shows that name", () => {
    expect(stepTitle(combineStep("Exported or secreted"), "combine")).toBe(
      "Exported or secreted",
    );
  });

  test("a search shows the name it was given", () => {
    const step: Step = { ...combineStep("Kinases"), kind: "search", operator: null };

    expect(stepTitle(step, "search")).toBe("Kinases");
  });
});

describe("stepSubtitle", () => {
  const exported: Step = {
    ...combineStep("Exported Protein", "GenesByExportPrediction"),
    kind: "search",
    operator: null,
    criterionText: "genes with a predicted GPI anchor",
  };

  test("a search is titled by what runs and subtitled by the request's words", () => {
    expect([stepTitle(exported, "search"), stepSubtitle(exported, "search")]).toEqual([
      "Exported Protein",
      "genes with a predicted GPI anchor",
    ]);
  });

  test("words that repeat the title are not shown twice", () => {
    const step: Step = { ...exported, criterionText: "Exported Protein" };

    expect(stepSubtitle(step, "search")).toBe("");
  });

  test("a step with no words has no subtitle", () => {
    const step: Step = { ...exported, criterionText: null };

    expect(stepSubtitle(step, "transform")).toBe("");
  });

  test("a combine has no subtitle", () => {
    expect(stepSubtitle({ ...exported, kind: "combine" }, "combine")).toBe("");
  });
});
