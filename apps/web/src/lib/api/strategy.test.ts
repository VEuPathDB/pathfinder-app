import { describe, expect, it } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import type { Strategy } from "@pathfinder/shared";
import { getStepRecordsQueryKey } from "@pathfinder/shared/generated/hooks/useGetStepRecords";
import { refetchStrategy, strategyQueryKey, writeStrategy } from "./strategy";

const STRATEGY: Strategy = {
  id: "conv-1",
  name: "kinases",
  siteId: "plasmodb",
  recordType: "transcript",
  rootStepId: null,
  isSaved: false,
  steps: [],
  description: null,
  wdkStrategyId: null,
  wdkUrl: null,
  createdAt: "2026-09-23T00:00:00Z",
  updatedAt: "2026-09-23T00:00:00Z",
};

function seededClient(): QueryClient {
  const client = new QueryClient();
  for (const [conversation, step, offset] of [
    ["conv-1", "step_1", 0],
    ["conv-1", "step_1", 50],
    ["conv-1", "step_2", 0],
    ["conv-2", "step_1", 0],
  ] as const) {
    client.setQueryData(
      [
        ...getStepRecordsQueryKey(conversation, step, {
          siteId: "plasmodb",
          offset,
          limit: 50,
        }),
        { wdkStepId: 22 },
      ],
      { records: [] },
    );
  }
  return client;
}

function invalidatedPages(client: QueryClient): string[] {
  return client
    .getQueryCache()
    .getAll()
    .filter((q) => q.state.isInvalidated)
    .map((q) => JSON.stringify(q.queryKey[0]) + JSON.stringify(q.queryKey[1]));
}

describe("writeStrategy", () => {
  it("stores the strategy and marks every step page of that conversation stale", () => {
    const client = seededClient();

    writeStrategy(client, "conv-1", STRATEGY);

    expect(client.getQueryData(strategyQueryKey("conv-1"))).toEqual(STRATEGY);
    expect(invalidatedPages(client)).toHaveLength(3);
    expect(invalidatedPages(client).every((key) => key.includes('"conv-1"'))).toBe(
      true,
    );
  });
});

describe("refetchStrategy", () => {
  it("marks the strategy and every step page of that conversation stale", async () => {
    const client = seededClient();
    client.setQueryData(strategyQueryKey("conv-1"), STRATEGY);

    await refetchStrategy(client, "conv-1");

    expect(client.getQueryState(strategyQueryKey("conv-1"))?.isInvalidated).toBe(true);
    expect(invalidatedPages(client)).toHaveLength(4);
    expect(
      client.getQueryCache().find({
        queryKey: [
          ...getStepRecordsQueryKey("conv-2", "step_1", {
            siteId: "plasmodb",
            offset: 0,
            limit: 50,
          }),
          { wdkStepId: 22 },
        ],
      })?.state.isInvalidated,
    ).toBe(false);
  });
});
