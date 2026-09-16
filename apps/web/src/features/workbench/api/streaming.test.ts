import { describe, expect, it, vi, beforeEach } from "vitest";
import type { CreateExperimentRequest } from "@pathfinder/shared/generated/types/CreateExperimentRequest";

const calls: Array<{ url: string; opts: { body?: unknown } }> = [];

vi.mock("@/lib/sse/typedEventStream", () => ({
  streamTypedEvents: (url: string, opts: { body?: unknown }) => {
    calls.push({ url, opts });
    return (async function* () {})();
  },
}));

import { createExperimentStream } from "./streaming";

async function drain(gen: AsyncGenerator<unknown>): Promise<void> {
  for await (const _ of gen) {
    void _;
  }
}

function request(overrides: Partial<CreateExperimentRequest> = {}) {
  return {
    siteId: "plasmodb",
    recordType: "transcript",
    mode: "single",
    searchName: "GenesByRNASeq",
    parameters: {},
    positiveControls: ["PF3D7_0100100"],
    negativeControls: ["PF3D7_0200200"],
    controlsSearchName: "GeneByLocusTag",
    controlsParamName: "ds_gene_ids",
    controlsValueFormat: "newline",
    name: "set (evaluation)",
    ...overrides,
  } satisfies CreateExperimentRequest;
}

describe("createExperimentStream", () => {
  beforeEach(() => {
    calls.length = 0;
  });

  it("POSTs the request it is given to the experiments endpoint", async () => {
    await drain(
      createExperimentStream(
        request({
          enableCrossValidation: true,
          kFolds: 5,
          targetGeneIds: ["PF3D7_0100100", "PF3D7_0300300"],
        }),
      ),
    );

    expect(calls).toHaveLength(1);
    expect(calls[0]?.url).toBe("/api/v1/experiments");
    const body = calls[0]?.opts.body as CreateExperimentRequest;
    expect(body.siteId).toBe("plasmodb");
    expect(body.mode).toBe("single");
    expect(body.controlsSearchName).toBe("GeneByLocusTag");
    expect(body.controlsParamName).toBe("ds_gene_ids");
    expect(body.positiveControls).toEqual(["PF3D7_0100100"]);
    expect(body.kFolds).toBe(5);
    expect(body.targetGeneIds).toEqual(["PF3D7_0100100", "PF3D7_0300300"]);
  });

  it("carries the gene set an evaluation was started from", async () => {
    await drain(createExperimentStream(request({ geneSetId: "gs-gametocyte" })));

    const body = calls[0]?.opts.body as CreateExperimentRequest;
    expect(body.geneSetId).toBe("gs-gametocyte");
  });

  it("names no gene set when the run did not start from one", async () => {
    await drain(createExperimentStream(request()));

    const body = calls[0]?.opts.body as CreateExperimentRequest;
    expect(body.geneSetId).toBe(undefined);
    expect(body.siteId).toBe("plasmodb");
  });
});
