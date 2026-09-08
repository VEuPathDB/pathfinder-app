import { describe, expect, it } from "vitest";
import type { UIMessage } from "ai";

import { EDA_ANALYSIS_STATE_FIXTURE } from "./edaPartFixtures";
import { isNewestAnalysisState, studyNameFor } from "./analysisStateParts";

const OLD = { ...EDA_ANALYSIS_STATE_FIXTURE, numComputations: 0 };
const NEW = { ...EDA_ANALYSIS_STATE_FIXTURE, numComputations: 1 };

function thread(states: object[]): UIMessage[] {
  return states.map((state, index) => ({
    id: `m${String(index)}`,
    role: "assistant",
    parts: [{ type: "data-eda.analysis-state", data: state }],
  }));
}

describe("isNewestAnalysisState", () => {
  it("keeps only the thread's last statement of an analysis", () => {
    const messages = thread([OLD, NEW]);
    expect(isNewestAnalysisState(messages, OLD)).toBe(false);
    expect(isNewestAnalysisState(messages, NEW)).toBe(true);
  });

  it("keeps a state of another analysis regardless", () => {
    const other = { ...OLD, analysisId: "AN_other" };
    expect(isNewestAnalysisState(thread([OLD, NEW]), other)).toBe(true);
  });
});

describe("studyNameFor", () => {
  it("reads the study name off the thread's last state for the analysis", () => {
    const messages = thread([OLD, NEW]);
    expect(studyNameFor(messages, NEW.analysisId)).toBe(NEW.studyDisplayName);
  });

  it("answers empty when the thread never stated the analysis", () => {
    expect(studyNameFor(thread([OLD]), "AN_other")).toBe("");
  });
});
