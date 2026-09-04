/**
 * The workbench streams run through the real SSE helper here, because the CSRF
 * middleware refuses any POST that omits `X-Requested-With`.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createBatchExperimentStream,
  createBenchmarkStream,
  createExperimentStream,
  type ExperimentRunConfig,
} from "./streaming";

const CONFIG: ExperimentRunConfig = {
  siteId: "plasmodb",
  recordType: "transcript",
  searchName: "GenesByRNASeqEvidence",
  positiveControls: ["PF3D7_1133400"],
};

function stubFetch(): ReturnType<typeof vi.fn> {
  const fetchSpy = vi.fn(
    async () =>
      new Response("data: [DONE]\n\n", {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      }),
  );
  vi.stubGlobal("fetch", fetchSpy);
  return fetchSpy;
}

async function drain(gen: AsyncGenerator<unknown>): Promise<void> {
  for await (const event of gen) {
    void event;
  }
}

function sentHeaders(fetchSpy: ReturnType<typeof vi.fn>): Record<string, string> {
  const call = fetchSpy.mock.calls[0] ?? [];
  return (call[1] as RequestInit).headers as Record<string, string>;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("workbench experiment streams", () => {
  it("sends the CSRF header when running an evaluation", async () => {
    const fetchSpy = stubFetch();
    await drain(createExperimentStream(CONFIG));
    expect(fetchSpy.mock.calls[0]?.[0]).toBe("/api/v1/experiments");
    expect(sentHeaders(fetchSpy)["X-Requested-With"]).toBe("XMLHttpRequest");
  });

  it("sends the CSRF header when running a batch", async () => {
    const fetchSpy = stubFetch();
    await drain(
      createBatchExperimentStream(CONFIG, "organism", [{ organism: "P. falciparum" }]),
    );
    expect(fetchSpy.mock.calls[0]?.[0]).toBe("/api/v1/experiments/batch");
    expect(sentHeaders(fetchSpy)["X-Requested-With"]).toBe("XMLHttpRequest");
  });

  it("sends the CSRF header when running a benchmark", async () => {
    const fetchSpy = stubFetch();
    await drain(
      createBenchmarkStream(CONFIG, [
        {
          label: "kinases",
          positiveControls: ["PF3D7_1133400"],
          negativeControls: ["PF3D7_0930300"],
          isPrimary: true,
        },
      ]),
    );
    expect(fetchSpy.mock.calls[0]?.[0]).toBe("/api/v1/experiments/benchmark");
    expect(sentHeaders(fetchSpy)["X-Requested-With"]).toBe("XMLHttpRequest");
  });
});
