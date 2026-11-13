/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { listAuditFindingsSuspenseQueryKey } from "@strategist/shared/generated/hooks/useListAuditFindingsSuspense";
import type { AuditRunSummaryPhaseEnumKey } from "@strategist/shared/generated/types/AuditRunSummary";
import { buildUrl } from "@/lib/api/http";

import { SAMPLE_RUN, SAMPLE_RUN_ID } from "./__fixtures__/sampleRun";
import { server } from "../../../vitest.msw-setup";
import { auditRunOptions, findingsCsvUrl, isLiveRun, runPollInterval } from "./api";

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

  it("keeps reading a finished run while its reviews run", () => {
    expect(runPollInterval({ ...SAMPLE_RUN, reviewsRunning: true })).toBe(5000);
    expect(isLiveRun({ ...SAMPLE_RUN, reviewsRunning: true })).toBe(true);
    expect(isLiveRun({ ...SAMPLE_RUN, reviewsRunning: false })).toBe(false);
  });
});

describe("the final read of a run's findings", () => {
  const RUN_URL = `http://localhost:3000/pathfinder/api/v1/audits/${SAMPLE_RUN_ID}`;
  const LIVE = { ...SAMPLE_RUN, run: { ...SAMPLE_RUN.run, phase: "running" as const } };
  const LIST_KEY = listAuditFindingsSuspenseQueryKey(SAMPLE_RUN_ID, { limit: 50 });

  async function readAfter(before: typeof SAMPLE_RUN, answer: typeof SAMPLE_RUN) {
    server.use(http.get(RUN_URL, () => HttpResponse.json(answer)));
    const client = new QueryClient();
    client.setQueryData(auditRunOptions(SAMPLE_RUN_ID).queryKey, before);
    client.setQueryData(LIST_KEY, { total: 0 });
    await client.fetchQuery({ ...auditRunOptions(SAMPLE_RUN_ID), staleTime: 0 });
    return client.getQueryState(LIST_KEY)?.isInvalidated;
  }

  it("reads the findings again when the run stops being live", async () => {
    expect(await readAfter(LIVE, SAMPLE_RUN)).toBe(true);
  });

  it("leaves the findings alone while the run stays live or stays finished", async () => {
    expect(await readAfter(LIVE, LIVE)).toBe(false);
    expect(await readAfter(SAMPLE_RUN, SAMPLE_RUN)).toBe(false);
  });

  it("reads the findings again when the reviews finish", async () => {
    expect(await readAfter({ ...SAMPLE_RUN, reviewsRunning: true }, SAMPLE_RUN)).toBe(
      true,
    );
  });
});
