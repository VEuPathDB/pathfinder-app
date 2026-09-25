import { describe, expect, it } from "vitest";

import {
  ExportedStepError,
  exportedStepPlacement,
  strategyFromExportedStep,
  unmatchedGenesSentence,
} from "./exportedStep";

const CONVERSATION_ID = "11111111-1111-4111-8111-111111111111";

function conversation(overrides: Record<string, unknown> = {}) {
  return {
    id: CONVERSATION_ID,
    name: "Heat shock",
    siteId: "plasmodb",
    recordType: "transcript",
    rootStepId: "step_eda",
    isSaved: false,
    createdAt: "2026-08-28T00:00:00Z",
    updatedAt: "2026-08-28T00:00:00Z",
    steps: [
      {
        id: "step_eda",
        searchName: "GenesByEdaVizWithCompute",
        displayName: "EDA volcano, 1543 genes",
        estimatedSize: 1543,
      },
    ],
    ...overrides,
  };
}

describe("strategyFromExportedStep", () => {
  it("reads the strategy the export answered with", () => {
    const strategy = strategyFromExportedStep(conversation());
    expect(strategy.steps.map((step) => step.id)).toEqual(["step_eda"]);
    expect(strategy.rootStepId).toBe("step_eda");
    expect(strategy.isSaved).toBe(false);
  });

  it("refuses a payload that is not a conversation", () => {
    expect(() => strategyFromExportedStep({ steps: [] })).toThrow(ExportedStepError);
    expect(() => strategyFromExportedStep({ steps: [] })).toThrow(
      "The export answered with a strategy the app cannot read.",
    );
  });

  it("refuses a strategy that carries no step", () => {
    expect(() =>
      strategyFromExportedStep(conversation({ steps: [], rootStepId: null })),
    ).toThrow("The export answered with no step.");
  });
});

describe("exportedStepPlacement", () => {
  it("says the export began the strategy when the step is its only root", () => {
    expect(exportedStepPlacement(strategyFromExportedStep(conversation()))).toEqual({
      kind: "begins-strategy",
      stepId: "step_eda",
    });
  });

  it("says the step is a draft root beside an existing strategy", () => {
    const payload = conversation({
      rootStepId: "step_wdk",
      steps: [
        { id: "step_wdk", searchName: "GenesByText", estimatedSize: 12 },
        {
          id: "step_eda",
          searchName: "GenesByEdaVizWithCompute",
          estimatedSize: 1543,
        },
      ],
    });
    expect(exportedStepPlacement(strategyFromExportedStep(payload))).toEqual({
      kind: "detached-draft",
      stepId: "step_eda",
    });
  });

  it("picks the newest detached root, and never a combine's input", () => {
    const payload = conversation({
      rootStepId: "step_combine",
      steps: [
        { id: "step_orphan", searchName: "GenesByLocation", estimatedSize: 40 },
        {
          id: "step_eda",
          searchName: "GenesByEdaVizWithCompute",
          estimatedSize: 1543,
        },
        {
          id: "step_combine",
          primaryInputStepId: "step_wdk_a",
          secondaryInputStepId: "step_wdk_b",
        },
        { id: "step_wdk_a", searchName: "GenesByText", estimatedSize: 12 },
        { id: "step_wdk_b", searchName: "GenesByGoTerm", estimatedSize: 105 },
      ],
    });
    expect(exportedStepPlacement(strategyFromExportedStep(payload))).toEqual({
      kind: "detached-draft",
      stepId: "step_eda",
    });
  });

  it("does not call an input step detached", () => {
    const payload = conversation({
      rootStepId: "step_combine",
      steps: [
        { id: "step_a", searchName: "GenesByText" },
        { id: "step_b", searchName: "GenesByLocation" },
        {
          id: "step_combine",
          primaryInputStepId: "step_a",
          secondaryInputStepId: "step_b",
        },
      ],
    });
    expect(exportedStepPlacement(strategyFromExportedStep(payload))).toEqual({
      kind: "begins-strategy",
      stepId: "step_combine",
    });
  });
});

describe("unmatchedGenesSentence", () => {
  it("names how many of the cut's genes the site's annotation lacks", () => {
    expect(unmatchedGenesSentence(201, 198, "PlasmoDB")).toBe(
      "3 of 201 genes are not genes of PlasmoDB's current annotation.",
    );
  });

  it("speaks of one gene in the singular", () => {
    expect(unmatchedGenesSentence(201, 200, "PlasmoDB")).toBe(
      "1 of 201 genes is not a gene of PlasmoDB's current annotation.",
    );
  });

  it("says nothing when the step holds every gene of the cut", () => {
    expect(unmatchedGenesSentence(201, 201, "PlasmoDB")).toBe(null);
  });

  it("says nothing when either count is unknown", () => {
    expect(unmatchedGenesSentence(201, null, "PlasmoDB")).toBe(null);
    expect(unmatchedGenesSentence(null, 198, "PlasmoDB")).toBe(null);
  });
});
