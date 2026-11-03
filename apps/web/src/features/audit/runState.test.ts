import { describe, expect, it } from "vitest";

import { SAMPLE_RUN, SAMPLE_WORDS } from "./__fixtures__/sampleRun";
import { currentStage, leftLines, leftLineText, stagesOf } from "./runState";

describe("runState", () => {
  it("counts what the sample run left, by status, across genomes, findings and evidence", () => {
    expect(leftLines(SAMPLE_RUN)).toEqual([
      { status: "unreached", genomes: 0, findings: 1, evidence: 1 },
      { status: "unread", genomes: 0, findings: 1, evidence: 1 },
    ]);
    expect(
      leftLines(SAMPLE_RUN).map((line) => leftLineText(line, SAMPLE_WORDS)),
    ).toEqual([
      "The site did not answer: 1 finding and 1 piece of evidence",
      "Not read before the run's deadline: 1 finding and 1 piece of evidence",
    ]);
    expect(currentStage(SAMPLE_RUN)).toBe(null);
  });

  it("counts a genome a run could not read and leaves out a status that holds none", () => {
    const genome = SAMPLE_RUN.genomes[0];
    if (genome === undefined) throw new Error("the sample run holds genomes");
    const view = {
      ...SAMPLE_RUN,
      counts: [],
      evidence: [],
      genomes: [{ ...genome, status: "failed" as const }],
    };
    expect(leftLines(view)).toEqual([
      { status: "failed", genomes: 1, findings: 0, evidence: 0 },
    ]);
    expect(
      leftLineText(
        { status: "failed", genomes: 2, findings: 3, evidence: 2 },
        SAMPLE_WORDS,
      ),
    ).toBe("Could not be read: 2 genomes, 3 findings and 2 pieces of evidence");
  });

  it("finds the first stage that has not finished", () => {
    const [first, second] = stagesOf(SAMPLE_RUN);
    if (first === undefined || second === undefined) {
      throw new Error("the sample run holds stages");
    }
    const open = { ...second, finished: false };
    const view = {
      ...SAMPLE_RUN,
      stages: {
        ...SAMPLE_RUN.stages,
        stages: [first, open, { ...open, name: "confirm" as const }],
      },
    };
    expect(currentStage(view)?.name).toBe("screen");
  });
});
