// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type { ConversationResponse, Strategy } from "@pathfinder/shared";

const refreshStepCounts = vi.hoisted(() => vi.fn());
vi.mock("@pathfinder/shared/generated/hooks/useRefreshStepCounts", () => ({
  refreshStepCounts: (...args: unknown[]) => refreshStepCounts(...args),
}));

const toastError = vi.hoisted(() => vi.fn());
vi.mock("sonner", () => ({ toast: { error: toastError } }));

import { getStepRecordsQueryKey } from "@pathfinder/shared/generated/hooks/useGetStepRecords";
import { strategyQueryKey } from "@/lib/api/strategy";
import { useRefreshStepCountsMutation } from "./useRefreshStepCountsMutation";

const CONVERSATION = "conv-1";
const SITE = "vectorbase";

function stale(): Strategy {
  return {
    id: CONVERSATION,
    name: "proteases",
    siteId: SITE,
    recordType: "transcript",
    rootStepId: "step_text",
    isSaved: false,
    steps: [
      {
        id: "step_text",
        kind: "search",
        displayName: "Genes by text",
        searchName: "GenesByText",
        recordType: "transcript",
        parameters: {},
        isFiltered: false,
        estimatedSize: 0,
      },
    ],
  } as Strategy;
}

function fresh(): ConversationResponse {
  const strategy = stale();
  return {
    ...strategy,
    steps: [{ ...strategy.steps[0]!, estimatedSize: 71 }],
  };
}

function harness(): {
  client: QueryClient;
  wrapper: (p: { children: ReactNode }) => ReactNode;
} {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  client.setQueryData(strategyQueryKey(CONVERSATION), stale());
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

describe("useRefreshStepCountsMutation", () => {
  afterEach(() => {
    refreshStepCounts.mockReset();
    toastError.mockReset();
  });

  it("asks the route once, for this thread on this site", async () => {
    refreshStepCounts.mockResolvedValue(fresh());
    const { wrapper } = harness();
    const { result } = renderHook(
      () =>
        useRefreshStepCountsMutation({ conversationId: CONVERSATION, siteId: SITE }),
      { wrapper },
    );

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(refreshStepCounts.mock.calls).toEqual([[CONVERSATION, { siteId: SITE }]]);
  });

  it("writes the returned counts into the strategy the panel reads", async () => {
    refreshStepCounts.mockResolvedValue(fresh());
    const { client, wrapper } = harness();
    const { result } = renderHook(
      () =>
        useRefreshStepCountsMutation({ conversationId: CONVERSATION, siteId: SITE }),
      { wrapper },
    );

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const cached = client.getQueryData<Strategy>(strategyQueryKey(CONVERSATION));
    expect(cached?.steps.map((step) => step.estimatedSize)).toEqual([71]);
  });

  it("reports a refusal through the toast and keeps the stored counts", async () => {
    refreshStepCounts.mockRejectedValue(new Error("vectorbase is not answering"));
    const { client, wrapper } = harness();
    const { result } = renderHook(
      () =>
        useRefreshStepCountsMutation({ conversationId: CONVERSATION, siteId: SITE }),
      { wrapper },
    );

    result.current.mutate();

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(toastError.mock.calls).toEqual([["vectorbase is not answering"]]);
    const cached = client.getQueryData<Strategy>(strategyQueryKey(CONVERSATION));
    expect(cached?.steps.map((step) => step.estimatedSize)).toEqual([0]);
  });

  it("marks the step answers stale when the counts come back", async () => {
    refreshStepCounts.mockResolvedValue(fresh());
    const { client, wrapper } = harness();
    const pageKey = [
      ...getStepRecordsQueryKey(CONVERSATION, "step_text", {
        siteId: SITE,
        offset: 0,
        limit: 50,
      }),
      { wdkStepId: 22 },
    ];
    client.setQueryData(pageKey, { records: [] });
    const { result } = renderHook(
      () =>
        useRefreshStepCountsMutation({ conversationId: CONVERSATION, siteId: SITE }),
      { wrapper },
    );

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(client.getQueryState(pageKey)?.isInvalidated).toBe(true);
  });
});
