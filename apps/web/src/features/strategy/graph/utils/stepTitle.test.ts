import { describe, expect, test } from "vitest";
import type { Step } from "@pathfinder/shared";
import { reasonDetail, stepReason, stepSubtitle, stepTitle } from "./stepTitle";

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

describe("stepTitle", () => {
  test.each([
    ["", "__combine__"],
    [WDK_DEFAULT, WDK_DEFAULT],
    ["Intersect", "__combine__"],
    ["Minus (reversed)", "__combine__"],
    ["Colocated", "__combine__"],
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

describe("stepReason", () => {
  const chosen: Step = {
    ...combineStep("Exported Protein", "GenesByExportPrediction"),
    kind: "search",
    operator: null,
    rationale: {
      kind: "search",
      searchName: "GenesByExportPrediction",
      basis: "nearest",
      term: "GPI anchor",
      reason: "no search states a GPI anchor; Exported Protein scored nearest",
      similarity: 0.44,
      compared: [
        { name: "GenesByText", displayName: "Gene Text Search", similarity: 0.41 },
        { name: "GenesWithSignalPeptide", displayName: "Predicted Signal Peptide" },
      ],
      toolCallId: "call_gpi",
      short: "nearest to GPI anchor",
    },
  };

  test("a search that says why shows the label the api wrote", () => {
    expect(stepReason(chosen, "search")).toBe("nearest to GPI anchor");
  });

  test("the detail is the reason and what the search was chosen over", () => {
    expect(chosen.rationale != null && reasonDetail(chosen.rationale)).toBe(
      "no search states a GPI anchor; Exported Protein scored nearest " +
        "(over Gene Text Search 0.41, Predicted Signal Peptide)",
    );
  });

  test("a measured step's detail is its counts, its size and its basis", () => {
    expect(
      reasonDetail({
        kind: "controls",
        taskId: "0c6100d2-0000-4000-8000-00000000a16a",
        searchName: "GenesByGoTerm",
        source: "enrichment",
        basis: "GO:0044217 other organism part",
        informs: "recovering",
        recovered: 42,
        positives: 80,
        admitted: 0,
        negatives: 40,
        resultSize: 637,
        term: "42 of 80 positives",
        short: "recovers 42 of 80 positives, admits 0 of 40 negatives",
      }),
    ).toBe(
      "chosen by the controls: recovers 42 of 80 positives, admits 0 of 40 " +
        "negatives, 637 genes (GO:0044217 other organism part)",
    );
  });

  test("a step with no reason and a combine show none", () => {
    expect([
      stepReason({ ...chosen, rationale: null }, "search"),
      stepReason(chosen, "combine"),
    ]).toEqual(["", ""]);
  });
});
