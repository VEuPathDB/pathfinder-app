import { describe, expect, it } from "vitest";

import served from "../../../../../../packages/spec/audit_words.json";

import {
  SAMPLE_DETAILS,
  SAMPLE_FINDINGS,
  SAMPLE_RUN,
  SAMPLE_RUN_ID,
  errorDetail,
  sampleDetail,
} from "./sampleRun";

describe("errorDetail", () => {
  it("skips a clean finding of the check for the errored one after it", () => {
    const clean = SAMPLE_DETAILS[2];
    const errored = SAMPLE_DETAILS[1];
    expect([clean?.finding.check, clean?.finding.errorType]).toEqual([
      "gene_length",
      null,
    ]);
    expect([errored?.finding.check, errored?.finding.errorType]).toEqual([
      "gene_length",
      "truncated_model",
    ]);
    const details = [clean, errored].flatMap((detail) =>
      detail === undefined ? [] : [detail],
    );
    expect(errorDetail(details, "gene_length").finding.id).toBe(2);
  });

  it("refuses a list that holds only clean findings of the check", () => {
    const clean = SAMPLE_DETAILS.filter(
      (detail) =>
        detail.finding.check === "gene_length" && detail.finding.errorType === null,
    );
    expect(clean.map((detail) => detail.finding.id)).toEqual([3, 4, 5, 6, 7]);
    expect(() => errorDetail(clean, "gene_length")).toThrow(
      "the sample run holds no gene_length error",
    );
  });
});

describe("the sample run", () => {
  it("parses the API's own bodies through the generated schemas", () => {
    expect([
      SAMPLE_RUN.run.id,
      SAMPLE_RUN.run.phase,
      SAMPLE_RUN.action,
      SAMPLE_RUN.left.total,
    ]).toEqual([SAMPLE_RUN_ID, "finished", "retry", 4]);
    expect(SAMPLE_FINDINGS.findings.map((finding) => finding.impact)).toEqual([
      0.5,
      0.25,
      0.25,
      0.25,
      0.25,
      null,
      null,
      null,
      null,
      null,
    ]);
    expect(SAMPLE_DETAILS).toHaveLength(10);
    expect(SAMPLE_DETAILS.map((detail) => detail.finding.id)).toEqual([
      1, 2, 3, 4, 5, 6, 7, 8, 9, 10,
    ]);
    expect(sampleDetail("strain_model").finding.genes.map((link) => link.gene)).toEqual(
      ["PcyM_0736700", "PCYB_074210"],
    );
    expect(sampleDetail("intron_support").finding.errorType).toBe("missing_exon");
  });

  it("refuses a check the sample holds no error of", () => {
    expect(() => sampleDetail("selenoprotein_end")).toThrow(
      "the sample run holds no selenoprotein_end error",
    );
  });

  it("names each check and error type in the words the API serves", () => {
    expect(
      SAMPLE_FINDINGS.findings.map((finding) => served.checks[finding.check]),
    ).toEqual(SAMPLE_FINDINGS.findings.map((finding) => finding.checkTitle));
    const pairs = SAMPLE_FINDINGS.findings.flatMap((finding) =>
      finding.errorType === null
        ? []
        : [[served.errorTypes[finding.errorType], finding.errorTitle]],
    );
    expect(pairs).toHaveLength(5);
    for (const [words, title] of pairs) expect(words).toBe(title);
  });
});
