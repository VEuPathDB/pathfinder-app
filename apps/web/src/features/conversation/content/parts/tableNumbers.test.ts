import { describe, expect, it } from "vitest";
import type { UIMessage } from "ai";
import type {
  ControlTestResults,
  EnrichmentResultsChunk,
  ScoredComparison,
} from "@pathfinder/shared";

import { tableNumberFor, tablePartFor } from "./tableNumbers";

type Part = UIMessage["parts"][number];

const CONTROLS: ControlTestResults = {
  taskId: "3d221443-0074-47d8-8300-addadd147989",
  toolCallId: "call_sLwqd6ToSyX9TDfOm62FTIT6",
  targetStepId: 440299573,
  targetLabel: "Genes by Molecular Weight",
  targetEstimatedSize: 132,
  positive: { controlsCount: 3, intersectionCount: 2, recall: 2 / 3 },
  negative: { controlsCount: 1, intersectionCount: 0, falsePositiveRate: 0 },
};

const ENRICHMENT: EnrichmentResultsChunk = {
  taskId: "t2",
  geneSetId: "gs-1",
  geneSetName: "Erythrocytic kinases",
  geneCount: 1342,
  results: [],
};

const SCORED: ScoredComparison = {
  objective: "mcc",
  winnerLabel: "v1",
  variants: [{ label: "v1", searchName: "SA", mcc: 0.42 }],
};

function part(type: string, data: object): Part {
  return { type, data } as Part;
}

function messagesOf(parts: Part[]): UIMessage[] {
  return [{ id: "m1", role: "assistant", parts }];
}

describe("tableNumberFor", () => {
  it("numbers the thread's tabular exhibits in emission order across kinds", () => {
    const messages = messagesOf([
      part("data-eda.viz", { chart: "volcano" }),
      part("data-control-test-results", CONTROLS),
      part("data-scored-comparison", SCORED),
      part("data-enrichment-results", ENRICHMENT),
    ]);

    expect(tableNumberFor(messages, CONTROLS)).toBe(1);
    expect(tableNumberFor(messages, SCORED)).toBe(2);
    expect(tableNumberFor(messages, ENRICHMENT)).toBe(3);
  });

  it("gives two numbers to two exhibits that carry equal payloads", () => {
    const first = { ...CONTROLS };
    const second = { ...CONTROLS };
    const messages = messagesOf([
      part("data-control-test-results", first),
      part("data-control-test-results", second),
    ]);

    expect(tableNumberFor(messages, first)).toBe(1);
    expect(tableNumberFor(messages, second)).toBe(2);
  });

  it("keeps a number where it is when a later message adds an exhibit", () => {
    const early = { ...CONTROLS };
    const late = { ...CONTROLS, taskId: "t9" };
    const streaming = messagesOf([part("data-control-test-results", early)]);
    expect(tableNumberFor(streaming, early)).toBe(1);

    const settled = [
      ...streaming,
      {
        id: "m2",
        role: "assistant" as const,
        parts: [part("data-control-test-results", late)],
      },
    ];
    expect(tableNumberFor(settled, early)).toBe(1);
    expect(tableNumberFor(settled, late)).toBe(2);
  });

  it("does not number a plot", () => {
    const plot = { chart: "volcano" };
    const messages = messagesOf([part("data-eda.viz", plot)]);
    expect(tableNumberFor(messages, CONTROLS)).toBe(null);
  });

  it("answers null when the thread does not carry the exhibit", () => {
    expect(tableNumberFor(messagesOf([]), CONTROLS)).toBe(null);
  });
});

describe("tablePartFor", () => {
  it("finds the control-test exhibit a task produced", () => {
    const messages = messagesOf([
      part("data-scored-comparison", SCORED),
      part("data-control-test-results", CONTROLS),
    ]);

    expect(tablePartFor(messages, CONTROLS.taskId)).toEqual({
      number: 2,
      toolCallId: CONTROLS.toolCallId,
    });
  });

  it("finds the enrichment exhibit a task produced, which names no call", () => {
    const messages = messagesOf([part("data-enrichment-results", ENRICHMENT)]);

    expect(tablePartFor(messages, "t2")).toEqual({ number: 1, toolCallId: null });
  });

  it("answers null for a task that produced no exhibit", () => {
    const messages = messagesOf([part("data-control-test-results", CONTROLS)]);
    expect(tablePartFor(messages, "another-task")).toBe(null);
  });
});
