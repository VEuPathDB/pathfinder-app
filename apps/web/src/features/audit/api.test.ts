/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import type { AuditRunSummaryPhaseEnumKey } from "@pathfinder/shared/generated/types/AuditRunSummary";
import { buildUrl } from "@/lib/api/http";

import { SAMPLE_RUN, SAMPLE_RUN_ID } from "./__fixtures__/sampleRun";
import { findingsCsvUrl, runPollInterval } from "./api";

describe("runPollInterval", () => {
  it("reads a run again every 5 s only while it is queued or running", () => {
    const at = (phase: AuditRunSummaryPhaseEnumKey) =>
      runPollInterval({ ...SAMPLE_RUN, run: { ...SAMPLE_RUN.run, phase } });
    expect([
      at("queued"),
      at("running"),
      at("halted"),
      at("finished"),
      at("not_started"),
      runPollInterval(undefined),
    ]).toEqual([5000, 5000, false, false, false, false]);
  });
});

describe("findingsCsvUrl", () => {
  it("names the run's CSV route at the API's address", () => {
    expect(findingsCsvUrl(SAMPLE_RUN_ID)).toBe(
      buildUrl(`/api/v1/audits/${SAMPLE_RUN_ID}/findings.csv`),
    );
  });
});
