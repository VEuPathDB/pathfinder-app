// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { Strategy } from "@pathfinder/shared";

const refreshStepCounts = vi.hoisted(() => vi.fn());
vi.mock("@pathfinder/shared/generated/hooks/useRefreshStepCounts", () => ({
  refreshStepCounts: (...args: unknown[]) => refreshStepCounts(...args),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () => "/vectorbase/conversation/conv-1",
}));

import { strategyQueryKey, useStrategyData } from "@/lib/api/strategy";
import { StrategyPanel } from "./StrategyPanel";

const CONVERSATION = "conv-1";
const SITE = "vectorbase";
const STEP = "step_text";

function strategy(size: number): Strategy {
  return {
    id: CONVERSATION,
    name: "proteases",
    siteId: SITE,
    recordType: "transcript",
    rootStepId: STEP,
    isSaved: false,
    steps: [
      {
        id: STEP,
        kind: "search",
        displayName: "Genes by text",
        searchName: "GenesByText",
        recordType: "transcript",
        parameters: {},
        isFiltered: false,
        estimatedSize: size,
      },
    ],
  } as Strategy;
}

/** The rail reads the strategy from the query cache and hands it down. */
function Rail() {
  return (
    <StrategyPanel
      strategy={useStrategyData(CONVERSATION)}
      siteId={SITE}
      conversationId={CONVERSATION}
    />
  );
}

function renderPanel(): QueryClient {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  client.setQueryData(strategyQueryKey(CONVERSATION), strategy(0));
  render(
    <QueryClientProvider client={client}>
      <Rail />
    </QueryClientProvider>,
  );
  return client;
}

function renderedCount(): string | null {
  const row = screen.getByTestId(`compact-step-row-${STEP}`);
  return within(row).getByText(/^[\d,.]+$/).textContent;
}

function button(): HTMLElement {
  return screen.getByRole("button", { name: "Refresh step counts" });
}

describe("StrategyPanel refresh", () => {
  afterEach(() => {
    cleanup();
    refreshStepCounts.mockReset();
  });

  it("asks the route once per click", async () => {
    refreshStepCounts.mockResolvedValue(strategy(71));
    renderPanel();

    fireEvent.click(button());

    await waitFor(() =>
      expect(refreshStepCounts.mock.calls).toEqual([[CONVERSATION, { siteId: SITE }]]),
    );
  });

  it("spins and refuses a second click while the read is open", async () => {
    refreshStepCounts.mockReturnValue(new Promise(() => undefined));
    renderPanel();

    fireEvent.click(button());

    await waitFor(() => expect(button().getAttribute("disabled")).toBe(""));
    expect(button().querySelector(".animate-spin")).not.toBe(null);
    fireEvent.click(button());
    expect(refreshStepCounts.mock.calls.length).toBe(1);
  });

  it("shows the counts the route answered", async () => {
    refreshStepCounts.mockResolvedValue(strategy(71));
    renderPanel();
    expect(renderedCount()).toBe("0");

    fireEvent.click(button());

    await waitFor(() => expect(renderedCount()).toBe("71"));
  });

  it("offers no refresh on a thread with no strategy", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <StrategyPanel strategy={null} siteId={SITE} conversationId={CONVERSATION} />
      </QueryClientProvider>,
    );

    expect(screen.queryByRole("button", { name: "Refresh step counts" })).toBe(null);
  });
});
