import { describe, expect, it, vi, beforeEach } from "vitest";

const calls: Array<{ url: string; opts: { body?: unknown } }> = [];

vi.mock("@/lib/sse/typedEventStream", () => ({
  streamTypedEvents: (url: string, opts: { body?: unknown }) => {
    calls.push({ url, opts });
    return (async function* () {})();
  },
}));

import { createExperimentStream, type ExperimentRunConfig } from "./streaming";

async function drain(gen: AsyncGenerator<unknown>): Promise<void> {
  for await (const _ of gen) {
    void _;
  }
}

describe("createExperimentStream serialization", () => {
  beforeEach(() => {
    calls.length = 0;
  });

  it("POSTs to the experiments endpoint with a valid request body", async () => {
    const config: ExperimentRunConfig = {
      siteId: "plasmodb",
      recordType: "transcript",
      searchName: "GenesByRNASeq",
      positiveControls: ["PF3D7_0100100"],
      negativeControls: ["PF3D7_0200200"],
      controlsValueFormat: "newline",
      enableCrossValidation: true,
      kFolds: 5,
      name: "set (evaluation)",
    };
    await drain(createExperimentStream(config));

    expect(calls).toHaveLength(1);
    expect(calls[0]?.url).toBe("/api/v1/experiments");
    const body = calls[0]?.opts.body as Record<string, unknown>;
    expect(body["siteId"]).toBe("plasmodb");
    expect(body["mode"]).toBe("single"); // defaulted, not undefined
    expect(body["controlsValueFormat"]).toBe("newline");
    expect(body["positiveControls"]).toEqual(["PF3D7_0100100"]);
    expect(body["kFolds"]).toBe(5);
  });
});
