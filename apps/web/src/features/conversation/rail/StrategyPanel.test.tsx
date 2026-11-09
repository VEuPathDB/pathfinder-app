// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { listStrategiesQueryOptions } from "@pathfinder/shared/generated/hooks/useListStrategies";
import type { Strategy } from "@pathfinder/shared";

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn(), back: vi.fn() }),
  usePathname: () => "/conversation/conv-1",
}));

vi.mock("@/state/strategy/useStepSnapshot", () => ({
  useStepSnapshot: () => ({
    step: null,
    lifecycleState: "idle",
    estimatedSize: 5,
    validationErrors: null,
    lastError: null,
    isBusy: false,
    isInvalid: false,
    isFailed: false,
  }),
}));

import { strategyCanvasUrl, strategyStepUrl } from "@/lib/routes";
import { EVIDENCE_CARD } from "../content/parts/evidenceCardFixture";
import { StrategyPanel } from "./StrategyPanel";

const STRATEGY: Strategy = {
  id: "conv-1",
  name: "S",
  siteId: "plasmodb",
  recordType: "gene",
  steps: [
    {
      id: "step_1",
      kind: "search",
      displayName: "Genes by taxon",
      searchName: "GenesByTaxon",
      recordType: "gene",
      parameters: {},
      isFiltered: false,
    },
  ],
  rootStepId: "step_1",
  isSaved: false,
  createdAt: "2026-01-01T00:00:00.000Z",
  updatedAt: "2026-01-01T00:00:00.000Z",
};

function renderChecked(check: Parameters<typeof StrategyPanel>[0]["check"]) {
  render(
    <StrategyPanel
      check={check}
      strategy={STRATEGY}
      siteId="plasmodb"
      conversationId="conv-1"
    />,
  );
}

const MATCHED = {
  ...EVIDENCE_CARD,
  steps: EVIDENCE_CARD.steps.map((step) => ({ ...step, drifted: false })),
};

describe("StrategyPanel headline", () => {
  afterEach(() => cleanup());

  it("shows the result count headline", () => {
    renderChecked(null);
    expect(screen.getByTestId("strategy-headline").textContent).toBe("5genes");
    expect(screen.queryByTestId("rail-strategy-footer")).toBeNull();
  });

  it("says the counts match", () => {
    renderChecked({ card: MATCHED, superseded: false });
    expect(screen.getByTestId("strategy-check").textContent).toBe(
      "Checked: every count matches PlasmoDB",
    );
  });

  it("says how many counts changed", () => {
    renderChecked({ card: EVIDENCE_CARD, superseded: false });
    expect(screen.getByTestId("strategy-check").textContent).toBe(
      "1 count changed on PlasmoDB since the build",
    );
  });

  it("says the check is stale", () => {
    renderChecked({ card: MATCHED, superseded: true });
    expect(screen.getByTestId("strategy-check").textContent).toBe(
      "Changed since the last check",
    );
  });

  it("says the site did not answer", () => {
    renderChecked({
      card: { ...MATCHED, siteRead: "not_answered" },
      superseded: false,
    });
    expect(screen.getByTestId("strategy-check").textContent).toBe(
      "PlasmoDB did not answer the check",
    );
  });
});

describe("StrategyPanel (read-only rail)", () => {
  afterEach(() => {
    cleanup();
    pushMock.mockReset();
  });

  it("shows empty state when no steps", () => {
    render(
      <StrategyPanel
        check={null}
        strategy={null}
        siteId="plasmodb"
        conversationId="conv-1"
      />,
    );
    expect(screen.getByText(/No strategy built yet/i)).toBeTruthy();
  });

  it("renders compact step list and Open button when steps exist", () => {
    render(
      <StrategyPanel
        check={null}
        strategy={STRATEGY}
        siteId="plasmodb"
        conversationId="conv-1"
      />,
    );
    expect(screen.getByTestId("compact-strategy-view")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Open editor" })).toBeTruthy();
  });

  it("Open button navigates to /strategy", () => {
    render(
      <StrategyPanel
        check={null}
        strategy={STRATEGY}
        siteId="plasmodb"
        conversationId="conv-1"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Open editor" }));
    expect(pushMock).toHaveBeenCalledWith(strategyCanvasUrl("conv-1"));
  });

  it("Clicking a step row navigates to /strategy/step/:id", () => {
    render(
      <StrategyPanel
        check={null}
        strategy={STRATEGY}
        siteId="plasmodb"
        conversationId="conv-1"
      />,
    );
    fireEvent.click(screen.getByTestId("compact-step-row-step_1"));
    expect(pushMock).toHaveBeenCalledWith(strategyStepUrl("conv-1", "step_1"));
  });

  it("offers Insert saved strategy when there is nothing built yet", () => {
    renderEmptyPanel();
    expect(screen.getByTestId("rail-strategy-insert-saved")).toBeVisible();
  });

  it("Insert saved strategy opens the picker", async () => {
    renderEmptyPanel();
    fireEvent.click(screen.getByTestId("rail-strategy-insert-saved"));
    expect(await screen.findByTestId("insert-saved-dialog")).toBeVisible();
  });
});

function renderEmptyPanel(): void {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, gcTime: Infinity },
    },
  });
  qc.setQueryData(listStrategiesQueryOptions({ siteId: "plasmodb" }).queryKey, []);
  render(
    <QueryClientProvider client={qc}>
      <StrategyPanel
        check={null}
        strategy={null}
        siteId="plasmodb"
        conversationId="conv-1"
      />
    </QueryClientProvider>,
  );
}
