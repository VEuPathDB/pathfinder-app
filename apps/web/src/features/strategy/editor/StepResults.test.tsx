// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type { Strategy } from "@pathfinder/shared";
import type {
  getStepRecords,
  getStepRecordsQueryKey,
} from "@pathfinder/shared/generated/hooks/useGetStepRecords";
import type { StepRecordsResponse } from "@pathfinder/shared/generated/types/StepRecordsResponse";
import { APIError } from "@/lib/api/http";
import { writeStrategy } from "@/lib/api/strategy";

const mockGetStepRecords = vi.fn<typeof getStepRecords>();
vi.mock(
  "@pathfinder/shared/generated/hooks/useGetStepRecords",
  async (importOriginal) => ({
    ...(await importOriginal<{
      getStepRecordsQueryKey: typeof getStepRecordsQueryKey;
    }>()),
    getStepRecords: (...args: Parameters<typeof getStepRecords>) =>
      mockGetStepRecords(...args),
  }),
);

import { StepResults } from "./StepResults";

const STEP_URL = "https://plasmodb.org/plasmo/app/workspace/strategies/11/22";

function geneId(n: number): string {
  return `PF3D7_${String(n).padStart(7, "0")}`;
}

function page(
  offset: number,
  count: number,
  total: number,
  first = offset,
): StepRecordsResponse {
  return {
    stepId: "step_1",
    wdkStepId: 22,
    total,
    offset,
    limit: 50,
    recordType: "transcript",
    stepUrl: STEP_URL,
    records: Array.from({ length: count }, (_, i) => ({
      geneId: geneId(first + i),
      organism: "Plasmodium falciparum 3D7",
      product: `product ${first + i}`,
      recordUrl: `https://plasmodb.org/plasmo/app/record/gene/${geneId(first + i)}`,
    })),
  };
}

function pending(): Promise<StepRecordsResponse> {
  return new Promise(() => {});
}

interface Props {
  stepId?: string;
  wdkStepId: number | null;
  estimatedSize?: number | null;
  hasUnsavedEdits?: boolean;
}

function element(props: Props) {
  return (
    <StepResults
      conversationId="conv-1"
      stepId={props.stepId ?? "step_1"}
      wdkStepId={props.wdkStepId}
      siteId="plasmodb"
      estimatedSize={props.estimatedSize ?? null}
      hasUnsavedEdits={props.hasUnsavedEdits ?? false}
    />
  );
}

function renderResults(props: Props) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, ...render(element(props), { wrapper }) };
}

function apiError(status: number, code: string, detail: string): APIError {
  return new APIError(detail, {
    status,
    statusText: "",
    url: "/api/v1/conversations/conv-1/strategy/steps/step_1/records",
    data: { code, detail },
  });
}

describe("StepResults", () => {
  afterEach(() => {
    cleanup();
    mockGetStepRecords.mockReset();
  });

  it("lists each gene with its record link, organism and product", async () => {
    mockGetStepRecords.mockResolvedValue(page(0, 2, 2));
    renderResults({ wdkStepId: 22 });

    const link = await screen.findByRole("link", { name: geneId(0) });
    expect(link.getAttribute("href")).toBe(
      `https://plasmodb.org/plasmo/app/record/gene/${geneId(0)}`,
    );
    expect(link.getAttribute("target")).toBe("_blank");
    const row = screen.getByTestId(`step-result-${geneId(1)}`);
    expect(within(row).getByText("Plasmodium falciparum 3D7").tagName).toBe("SPAN");
    expect(within(row).getByTitle("product 1").textContent).toBe("product 1");
    expect(screen.getByText("2 genes").textContent).toBe("2 genes");
    expect(mockGetStepRecords).toHaveBeenCalledWith(
      "conv-1",
      "step_1",
      { siteId: "plasmodb", offset: 0, limit: 50 },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it("opens the step result on the site", async () => {
    mockGetStepRecords.mockResolvedValue(page(0, 1, 1));
    renderResults({ wdkStepId: 22 });

    const open = await screen.findByRole("link", { name: /Open in PlasmoDB/ });
    expect(open.getAttribute("href")).toBe(STEP_URL);
    expect(open.getAttribute("rel")).toBe("noreferrer");
  });

  it("is open by default and collapses on its header", async () => {
    mockGetStepRecords.mockResolvedValue(page(0, 1, 1));
    renderResults({ wdkStepId: 22 });

    await screen.findByRole("link", { name: geneId(0) });
    const trigger = screen.getByRole("button", { name: /Results/ });
    expect(trigger.getAttribute("aria-expanded")).toBe("true");

    await userEvent.click(trigger);

    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("link", { name: geneId(0) })).toBeNull();
  });

  it("says the step is not on the site and fetches nothing without a wdk id", () => {
    renderResults({ wdkStepId: null });

    expect(screen.getByText("Not on the site yet").textContent).toBe(
      "Not on the site yet",
    );
    expect(mockGetStepRecords).not.toHaveBeenCalled();
  });

  it("says the step is not on the site when the server answers 409 INVALID_STRATEGY", async () => {
    mockGetStepRecords.mockRejectedValue(
      apiError(409, "INVALID_STRATEGY", "Step step_1 is not on the site yet."),
    );
    renderResults({ wdkStepId: 22 });

    const text = await screen.findByText("Not on the site yet");
    expect(text.textContent).toBe("Not on the site yet");
  });

  it("shows the message of a 409 with another code", async () => {
    mockGetStepRecords.mockRejectedValue(
      apiError(409, "CONFLICT", "The strategy is being written"),
    );
    renderResults({ wdkStepId: 22 });

    const text = await screen.findByText("The strategy is being written");
    expect(text.textContent).toBe("The strategy is being written");
    expect(screen.queryByText("Not on the site yet")).toBeNull();
  });

  it("shows the error message and no count for another failure", async () => {
    mockGetStepRecords.mockRejectedValue(
      apiError(503, "SITE_UNAVAILABLE", "PlasmoDB did not respond"),
    );
    renderResults({ wdkStepId: 22, estimatedSize: 1234 });

    const text = await screen.findByText("PlasmoDB did not respond");
    expect(text.textContent).toBe("PlasmoDB did not respond");
    expect(screen.queryByText("1,234 genes")).toBeNull();
  });

  it("shows the step count and three skeleton rows while the first page loads", () => {
    mockGetStepRecords.mockReturnValue(pending());
    renderResults({ wdkStepId: 22, estimatedSize: 1234 });

    expect(screen.getByText("1,234 genes").textContent).toBe("1,234 genes");
    expect(
      screen
        .getByTestId("step-results-loading")
        .querySelectorAll('[data-slot="skeleton"]'),
    ).toHaveLength(3);
  });

  it("appends the next page on Show more until the total is reached", async () => {
    mockGetStepRecords.mockImplementation(async (_c, _s, params) =>
      (params.offset ?? 0) === 0 ? page(0, 50, 60) : page(50, 10, 60),
    );
    renderResults({ wdkStepId: 22 });

    await screen.findByRole("link", { name: geneId(49) });
    await userEvent.click(screen.getByRole("button", { name: "Show more" }));

    await screen.findByRole("link", { name: geneId(59) });
    expect(mockGetStepRecords).toHaveBeenLastCalledWith(
      "conv-1",
      "step_1",
      { siteId: "plasmodb", offset: 50, limit: 50 },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.getAllByTestId(/^step-result-/)).toHaveLength(60);
    expect(screen.queryByRole("button", { name: "Show more" })).toBeNull();
  });

  it("offers no further page when a page comes back empty under the total", async () => {
    mockGetStepRecords.mockImplementation(async (_c, _s, params) =>
      (params.offset ?? 0) === 0 ? page(0, 50, 80) : page(50, 0, 80),
    );
    renderResults({ wdkStepId: 22 });

    await screen.findByRole("link", { name: geneId(49) });
    await userEvent.click(screen.getByRole("button", { name: "Show more" }));

    await waitFor(() => expect(mockGetStepRecords).toHaveBeenCalledTimes(2));
    expect(screen.getAllByTestId(/^step-result-/)).toHaveLength(50);
    expect(screen.queryByRole("button", { name: "Show more" })).toBeNull();
  });

  it("goes back to one loading page with no old rows on another step", async () => {
    mockGetStepRecords.mockImplementation(async (_c, _s, params) =>
      (params.offset ?? 0) === 0 ? page(0, 50, 60) : page(50, 10, 60),
    );
    const { rerender } = renderResults({ wdkStepId: 22 });
    await screen.findByRole("link", { name: geneId(49) });
    await userEvent.click(screen.getByRole("button", { name: "Show more" }));
    await screen.findByRole("link", { name: geneId(59) });

    mockGetStepRecords.mockReset();
    mockGetStepRecords.mockReturnValue(pending());
    rerender(element({ stepId: "step_2", wdkStepId: 23 }));

    expect(screen.queryAllByTestId(/^step-result-/)).toHaveLength(0);
    expect(
      screen
        .getByTestId("step-results-loading")
        .querySelectorAll('[data-slot="skeleton"]'),
    ).toHaveLength(3);
    expect(mockGetStepRecords.mock.calls.map((call) => [call[1], call[2]])).toEqual([
      ["step_2", { siteId: "plasmodb", offset: 0, limit: 50 }],
    ]);
  });

  it("reads the step again after a strategy write with the same wdk step id", async () => {
    mockGetStepRecords.mockResolvedValueOnce(page(0, 1, 1, 100));
    const { client } = renderResults({ wdkStepId: 22 });
    await screen.findByRole("link", { name: geneId(100) });

    mockGetStepRecords.mockResolvedValueOnce(page(0, 1, 1, 200));
    const strategy: Strategy = {
      id: "conv-1",
      name: "kinases",
      siteId: "plasmodb",
      recordType: "transcript",
      rootStepId: "step_1",
      isSaved: false,
      steps: [],
      description: null,
      wdkStrategyId: null,
      wdkUrl: null,
      createdAt: "2026-09-23T00:00:00Z",
      updatedAt: "2026-09-23T00:00:00Z",
    };
    act(() => writeStrategy(client, "conv-1", strategy));

    await screen.findByRole("link", { name: geneId(200) });
    expect(screen.queryByRole("link", { name: geneId(100) })).toBeNull();
    expect(mockGetStepRecords).toHaveBeenCalledTimes(2);
  });

  it("notes that results are for the saved step only when there are edits", async () => {
    mockGetStepRecords.mockResolvedValue(page(0, 1, 1));
    const { unmount } = renderResults({ wdkStepId: 22, hasUnsavedEdits: false });
    await screen.findByRole("link", { name: geneId(0) });
    expect(screen.queryByText("Results are for the saved step")).toBeNull();
    unmount();

    renderResults({ wdkStepId: 22, hasUnsavedEdits: true });
    const note = await screen.findByText("Results are for the saved step");
    expect(note.textContent).toBe("Results are for the saved step");
  });
});
