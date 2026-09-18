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

import { SavedStrategiesPage } from "./SavedStrategiesPage";
import { deleteStrategy } from "@pathfinder/shared/generated/hooks/useDeleteStrategy";
import { beginStrategy } from "@pathfinder/shared/generated/hooks/useBeginStrategy";
import { insertSavedStrategy } from "@/lib/api/conversations";
import { toast } from "sonner";
import { chatRoot, chatUrl } from "@/lib/routes";
import { useRightRailStore } from "@/state/useRightRailStore";

vi.mock("@pathfinder/shared/generated/hooks/useDeleteStrategy", () => ({
  deleteStrategy: vi.fn(() => Promise.resolve({})),
}));
vi.mock("@pathfinder/shared/generated/hooks/useBeginStrategy", () => ({
  beginStrategy: vi.fn(() => Promise.resolve({})),
}));
vi.mock("@/lib/api/conversations", () => ({
  insertSavedStrategy: vi.fn(() =>
    Promise.resolve({
      wdkStrategyId: 330659663,
      insertedSavedWdkStrategyId: 101,
      insertedSavedName: "Kinase sweep",
      combineStepId: "step_aa2f81cc",
    }),
  ),
}));
const routerPushMock = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: routerPushMock }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mockDelete = vi.mocked(deleteStrategy);
const mockBegin = vi.mocked(beginStrategy);
const mockInsert = vi.mocked(insertSavedStrategy);
const mockToastError = vi.mocked(toast.error);

function begunConversationId(): string {
  const call = mockBegin.mock.calls[0];
  if (call === undefined) throw new Error("begin was never called");
  return call[0];
}

function conv(over: Partial<ConversationResponse>): ConversationResponse {
  return {
    id: "c1",
    name: "Conv",
    siteId: "plasmodb",
    recordType: "transcript",
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    ...over,
  };
}

function renderPage(
  convs: ConversationResponse[],
  counts: Record<number, number> = {},
): void {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, gcTime: Infinity },
    },
  });
  qc.setQueryData(listStrategiesQueryOptions({ siteId: "plasmodb" }).queryKey, convs);
  qc.setQueryData(["saved-strategy-consumers", "plasmodb"], counts);
  const ui: ReactElement = (
    <QueryClientProvider client={qc}>
      <SavedStrategiesPage siteId="plasmodb" />
    </QueryClientProvider>
  );
  render(ui);
}

afterEach(cleanup);
beforeEach(() => {
  mockDelete.mockClear();
  mockBegin.mockClear();
  mockInsert.mockClear();
  mockToastError.mockClear();
  routerPushMock.mockClear();
  useRightRailStore.setState({ openPanel: null });
});

const KINASES = conv({
  id: "k1",
  name: "Kinase sweep",
  isSaved: true,
  wdkStrategyId: 101,
  stepCount: 3,
  estimatedSize: 1234,
  recordType: "transcript",
});
const PHOSPH = conv({
  id: "p1",
  name: "Phosphatase set",
  isSaved: true,
  wdkStrategyId: 202,
  stepCount: 1,
});
const DRAFT = conv({ id: "d1", name: "Unsaved draft", isSaved: false });
const INSERT_REFUSAL =
  "'Gametocyte combine block' was not inserted: the site refused the step 'Combine Gene results': bq_operator: Cannot be empty.";
const INSERT_RESULT = {
  wdkStrategyId: 330659663,
  insertedSavedWdkStrategyId: 101,
  insertedSavedName: "Kinase sweep",
  combineStepId: "step_aa2f81cc",
};

describe("SavedStrategiesPage", () => {
  it("lists only saved strategies with their step count, size and record type", async () => {
    renderPage([KINASES, DRAFT, PHOSPH], { 101: 0, 202: 0 });
    const list = await screen.findByTestId("saved-strategies-list");

    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(2);

    const kinaseRow = screen.getByTestId("saved-strategy-k1");
    expect(kinaseRow).toHaveTextContent("Kinase sweep");
    expect(kinaseRow).toHaveTextContent("3 steps · 1,234 results · transcript");

    const phosphRow = screen.getByTestId("saved-strategy-p1");
    expect(phosphRow).toHaveTextContent("1 step");

    expect(screen.queryByTestId("saved-strategy-d1")).toBeNull();
  });

  it("shows the consumer badge with the imported-by count", async () => {
    renderPage([KINASES], { 101: 3 });
    const row = await screen.findByTestId("saved-strategy-k1");
    expect(within(row).getByText("3 consumers").textContent).toBe("3 consumers");
  });

  it("filters the visible rows by name", async () => {
    renderPage([KINASES, PHOSPH], { 101: 0, 202: 0 });
    await screen.findByTestId("saved-strategies-list");

    await userEvent.type(screen.getByTestId("saved-strategies-filter"), "phosph");

    expect(screen.queryByTestId("saved-strategy-k1")).toBeNull();
    expect(screen.getByTestId("saved-strategy-p1")).toHaveTextContent(
      "Phosphatase set",
    );
  });

  it("shows the empty state when there are no saved strategies", async () => {
    renderPage([DRAFT]);
    const message = await screen.findByText("No saved strategies yet.");
    expect(message.textContent).toBe("No saved strategies yet.");
    expect(screen.queryByTestId("saved-strategies-list")).toBeNull();
  });

  it("points the empty-state chat link at the chat root of the site", async () => {
    renderPage([DRAFT]);
    const link = await screen.findByRole("link", { name: "start a new chat" });
    expect(link.getAttribute("href")).toBe(chatRoot("plasmodb"));
  });

  it("opens the row's conversation at its chat route", async () => {
    renderPage([KINASES], { 101: 0 });
    await screen.findByTestId("saved-strategy-k1");

    await userEvent.click(screen.getByText("Kinase sweep"));

    expect(routerPushMock.mock.calls).toEqual([[chatUrl("plasmodb", "k1")]]);
  });

  it("deletes a saved strategy from WDK with cascade on click", async () => {
    renderPage([KINASES], { 101: 0 });
    await screen.findByTestId("saved-strategy-k1");

    await userEvent.click(screen.getByTestId("saved-strategy-delete-k1"));

    await waitFor(() =>
      expect(mockDelete.mock.calls).toEqual([
        ["k1", { deleteFromWdk: true, cascade: true }],
      ]),
    );
  });

  it("Use in new chat opens a chat that starts from the saved strategy", async () => {
    renderPage([KINASES], { 101: 0 });
    await screen.findByTestId("saved-strategy-k1");

    await userEvent.click(screen.getByTestId("saved-strategy-use-k1"));

    await waitFor(() => expect(mockInsert).toHaveBeenCalledTimes(1));
    const conversationId = begunConversationId();
    expect(mockBegin.mock.calls).toEqual([
      [conversationId, { siteId: "plasmodb", seedText: "Kinase sweep" }],
    ]);
    expect(mockInsert.mock.calls).toEqual([
      [
        {
          conversationId,
          siteId: "plasmodb",
          targetStepId: "",
          savedWdkStrategyId: 101,
        },
      ],
    ]);
    await waitFor(() =>
      expect(routerPushMock.mock.calls).toEqual([
        [chatUrl("plasmodb", conversationId)],
      ]),
    );
  });

  it("removes the chat it opened when the insert is refused", async () => {
    mockInsert.mockRejectedValueOnce(new Error(INSERT_REFUSAL));
    renderPage([KINASES], { 101: 0 });
    await screen.findByTestId("saved-strategy-k1");

    await userEvent.click(screen.getByTestId("saved-strategy-use-k1"));

    await waitFor(() => expect(mockToastError).toHaveBeenCalledTimes(1));
    expect(mockDelete.mock.calls).toEqual([[begunConversationId()]]);
    expect(routerPushMock.mock.calls).toEqual([]);
  });

  it("names the saved strategy, the reason and what it removed", async () => {
    mockInsert.mockRejectedValueOnce(new Error(INSERT_REFUSAL));
    renderPage([KINASES], { 101: 0 });
    await screen.findByTestId("saved-strategy-k1");

    await userEvent.click(screen.getByTestId("saved-strategy-use-k1"));

    await waitFor(() => expect(mockToastError).toHaveBeenCalledTimes(1));
    expect(mockToastError.mock.calls).toEqual([
      [
        'Could not use "Kinase sweep" in a new chat',
        {
          description: `${INSERT_REFUSAL} The empty chat it opened was removed.`,
        },
      ],
    ]);
  });

  it("says the chat is still there when it cannot be removed", async () => {
    mockInsert.mockRejectedValueOnce(new Error(INSERT_REFUSAL));
    mockDelete.mockRejectedValueOnce(new Error("HTTP 500"));
    renderPage([KINASES], { 101: 0 });
    await screen.findByTestId("saved-strategy-k1");

    await userEvent.click(screen.getByTestId("saved-strategy-use-k1"));

    await waitFor(() => expect(mockToastError).toHaveBeenCalledTimes(1));
    expect(mockToastError.mock.calls[0]?.[1]).toEqual({
      description: `${INSERT_REFUSAL} The empty chat it opened is still in the sidebar.`,
    });
  });

  it("reports the insert while it runs", async () => {
    let finish: () => void = () => undefined;
    mockInsert.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = () => resolve(INSERT_RESULT);
        }),
    );
    renderPage([KINASES], { 101: 0 });
    await screen.findByTestId("saved-strategy-k1");

    await userEvent.click(screen.getByTestId("saved-strategy-use-k1"));

    await waitFor(() => expect(mockInsert).toHaveBeenCalledTimes(1));
    const button = screen.getByTestId("saved-strategy-use-k1");
    expect(button).toHaveTextContent("Inserting...");
    expect(button).toHaveAttribute("aria-busy", "true");

    finish();
    await waitFor(() =>
      expect(routerPushMock.mock.calls).toEqual([
        [chatUrl("plasmodb", begunConversationId())],
      ]),
    );
  });

  it("opens the new conversation with its strategy on show", async () => {
    renderPage([KINASES], { 101: 0 });
    await screen.findByTestId("saved-strategy-k1");

    await userEvent.click(screen.getByTestId("saved-strategy-use-k1"));

    await waitFor(() =>
      expect(useRightRailStore.getState().openPanel).toBe("strategy"),
    );
    expect(routerPushMock.mock.calls).toEqual([
      [chatUrl("plasmodb", begunConversationId())],
    ]);
  });
});
