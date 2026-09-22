/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import type { ConversationResponse } from "@pathfinder/shared/generated/types/ConversationResponse";
import { listStrategiesQueryOptions } from "@pathfinder/shared/generated/hooks/useListStrategies";
import { getStepRecordsQueryKey } from "@pathfinder/shared/generated/hooks/useGetStepRecords";

import { InsertSavedDialog } from "./InsertSavedDialog";
import { client } from "@/lib/api/client";

vi.mock("@/lib/api/client", () => ({
  client: vi.fn(() =>
    Promise.resolve({
      data: {
        wdkStrategyId: 7,
        insertedSavedWdkStrategyId: 11,
        insertedSavedName: "Alpha set",
        combineStepId: "combine-1",
      },
    }),
  ),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mockClient = vi.mocked(client);

function conv(over: Partial<ConversationResponse>): ConversationResponse {
  return {
    id: "x",
    name: "Conv",
    siteId: "plasmodb",
    recordType: "transcript",
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    ...over,
  };
}

const ELIGIBLE = [
  conv({ id: "a", name: "Alpha set", isSaved: true, wdkStrategyId: 11, stepCount: 2 }),
  conv({ id: "b", name: "Beta set", isSaved: true, wdkStrategyId: 22, stepCount: 1 }),
  conv({ id: "current", name: "Self", isSaved: true, wdkStrategyId: 99 }),
  conv({ id: "n", name: "No WDK", isSaved: true, wdkStrategyId: null }),
  conv({ id: "u", name: "Unsaved", isSaved: false, wdkStrategyId: 33 }),
];

function renderDialog(convs = ELIGIBLE, targetStepId = "step-x"): QueryClient {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, gcTime: Infinity },
    },
  });
  qc.setQueryData(listStrategiesQueryOptions({ siteId: "plasmodb" }).queryKey, convs);
  const ui: ReactElement = (
    <QueryClientProvider client={qc}>
      <InsertSavedDialog
        open
        onOpenChange={vi.fn()}
        conversationId="current"
        siteId="plasmodb"
        targetStepId={targetStepId}
      />
    </QueryClientProvider>
  );
  render(ui);
  return qc;
}

afterEach(cleanup);
beforeEach(() => mockClient.mockClear());

describe("InsertSavedDialog", () => {
  it("lists only eligible saved strategies, sorted by name", async () => {
    renderDialog();
    const picks = await screen.findAllByTestId(/^insert-saved-pick-/);
    expect(picks.map((p) => p.getAttribute("data-testid"))).toEqual([
      "insert-saved-pick-11",
      "insert-saved-pick-22",
    ]);
    expect(within(picks[0]!).getByText("Alpha set")).toBeTruthy();
    expect(within(picks[0]!).getByText("2 steps · transcript")).toBeTruthy();
  });

  it("keeps Insert disabled until a strategy is picked", async () => {
    renderDialog();
    const confirm = await screen.findByTestId("insert-saved-confirm");
    expect(confirm).toBeDisabled();

    await userEvent.click(screen.getByTestId("insert-saved-pick-11"));
    expect(confirm).toBeEnabled();
  });

  it("posts the picked strategy id, operator and target step on Insert", async () => {
    renderDialog();
    await screen.findByTestId("insert-saved-pick-22");

    await userEvent.click(screen.getByTestId("insert-saved-pick-22"));
    await userEvent.selectOptions(screen.getByLabelText("Operator"), "UNION");
    await userEvent.click(screen.getByTestId("insert-saved-confirm"));

    await waitFor(() => expect(mockClient).toHaveBeenCalledTimes(1));
    expect(mockClient).toHaveBeenCalledWith({
      method: "post",
      url: "/api/v1/conversations/current/insert-saved",
      params: { siteId: "plasmodb" },
      data: {
        targetStepId: "step-x",
        savedWdkStrategyId: 22,
        operator: "UNION",
      },
    });
  });

  it("marks the thread's step answers stale after the insert", async () => {
    const qc = renderDialog();
    const pageKey = [
      ...getStepRecordsQueryKey("current", "step-x", {
        siteId: "plasmodb",
        offset: 0,
        limit: 50,
      }),
      { wdkStepId: 22 },
    ];
    qc.setQueryData(pageKey, { records: [] });
    await userEvent.click(await screen.findByTestId("insert-saved-pick-22"));
    await userEvent.click(screen.getByTestId("insert-saved-confirm"));

    await waitFor(() => {
      expect(qc.getQueryState(pageKey)?.isInvalidated).toBe(true);
    });
  });

  it("defaults the operator to INTERSECT", async () => {
    renderDialog();
    const operator = await screen.findByLabelText<HTMLSelectElement>("Operator");
    expect(operator.value).toBe("INTERSECT");
  });

  it("filters the pick list by name", async () => {
    renderDialog();
    await screen.findByTestId("insert-saved-pick-11");

    await userEvent.type(
      screen.getByPlaceholderText("Filter saved strategies..."),
      "beta",
    );

    const picks = screen.getAllByTestId(/^insert-saved-pick-/);
    expect(picks.map((p) => p.getAttribute("data-testid"))).toEqual([
      "insert-saved-pick-22",
    ]);
  });

  it("drops the operator picker when there is no step to combine with", async () => {
    renderDialog(ELIGIBLE, "");
    expect(await screen.findByTestId("insert-saved-pick-11")).toBeVisible();
    expect(screen.queryByLabelText("Operator")).toBeNull();
  });

  it("posts an empty target and no operator when it becomes the root", async () => {
    renderDialog(ELIGIBLE, "");
    await screen.findByTestId("insert-saved-pick-11");

    await userEvent.click(screen.getByTestId("insert-saved-pick-11"));
    await userEvent.click(screen.getByTestId("insert-saved-confirm"));

    await waitFor(() => expect(mockClient).toHaveBeenCalledTimes(1));
    expect(mockClient).toHaveBeenCalledWith({
      method: "post",
      url: "/api/v1/conversations/current/insert-saved",
      params: { siteId: "plasmodb" },
      data: { targetStepId: "", savedWdkStrategyId: 11 },
    });
  });
});
