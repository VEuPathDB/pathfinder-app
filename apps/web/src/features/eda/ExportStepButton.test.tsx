/**
 * @vitest-environment jsdom
 */
import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { QueryClientProvider } from "@tanstack/react-query";

const toastError = vi.fn();
vi.mock("sonner", () => ({ toast: { error: (m: string) => toastError(m) } }));

import { createTestQueryClient } from "@/lib/query/testing";
import { getStepRecordsQueryKey } from "@pathfinder/shared/generated/hooks/useGetStepRecords";
import { strategyQueryKey } from "@/lib/api/strategy";
import { useEdaStore } from "@/state/eda";
import { appQueryClientWrapper } from "@/app/components/__fixtures__/appQueryClient";
import { ExportStepButton } from "./ExportStepButton";

const BASE = "http://localhost:3000";
const server = setupServer();
const CONVERSATION_UUID = "11111111-1111-4111-8111-111111111111";

function analysis(overrides: Record<string, unknown> = {}) {
  return {
    siteId: "plasmodb",
    datasetId: "DS_e973eadd57",
    studyId: "STUDY_e973eadd57",
    analysisId: "a-1",
    revision: 0,
    studyDisplayName: "Heat shock response",
    displayName: "Unsaved analysis",
    numFilters: 0,
    numComputations: 1,
    filters: [],
    filterSummaries: [],
    entityCounts: [],
    canExportRows: true,
    ...overrides,
  };
}

// The api's refusal of one sample filter and no computation, as the tab shows it.
const SAMPLE_ONLY_REFUSAL =
  "The analysis holds 1 filter on Sample and 0 comparisons, and no filter " +
  "on pfal3D7 htseq counts. A step holds genes, and a subset of another " +
  "entity selects no genes, so nothing was written. Run a differential " +
  "expression comparison and export the genes that pass its cut, or add a " +
  "filter on pfal3D7 htseq counts.";

/** A figure of the analysis's comparison, read with the cut the analysis stores. */
function figure(overrides: Record<string, unknown> = {}) {
  return {
    datasetId: "DS_e973eadd57",
    analysisId: "a-1",
    chart: "volcano" as const,
    effectSizeLabel: "log2(Fold Change)",
    effectSizeThreshold: 1,
    significanceThreshold: 0.05,
    effectDirection: "upAndDown" as const,
    totalPoints: 1,
    retainedPoints: 1,
    points: [
      {
        pointId: "PF3D7_0100200",
        effectSize: 3.94,
        pValue: 0.00002,
        adjustedPValue: 0.00014,
        retained: true,
      },
    ],
    comparison: { groupA: ["normal"], groupB: ["febrile"] },
    ...overrides,
  };
}

const EDA_STEP = {
  id: "step_eda",
  searchName: "GenesByEdaVizWithCompute",
  displayName: "Genes higher in febrile than in normal",
  estimatedSize: 1543,
};

/** The refreshed strategy the export answers with, as the strategy routes
 * serialize it. */
function strategyPayload(overrides: Record<string, unknown> = {}) {
  return {
    id: CONVERSATION_UUID,
    name: "Heat shock",
    siteId: "plasmodb",
    recordType: "transcript",
    rootStepId: "step_eda",
    isSaved: false,
    createdAt: "2026-08-28T00:00:00Z",
    updatedAt: "2026-08-28T00:00:00Z",
    steps: [EDA_STEP],
    ...overrides,
  };
}

const BESIDE_EXISTING = strategyPayload({
  rootStepId: "step_wdk",
  steps: [
    {
      id: "step_wdk",
      searchName: "GenesByText",
      displayName: "Genes by text",
      estimatedSize: 12,
      wdkStepId: 990001,
    },
    EDA_STEP,
  ],
});

function answersWith(body: Record<string, unknown>) {
  server.use(
    http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
      HttpResponse.json(body),
    ),
  );
}

function readyToExport() {
  useEdaStore.getState().applyAnalysisState(analysis());
  useEdaStore.getState().applyViz(figure());
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
beforeEach(() => {
  toastError.mockClear();
  useEdaStore.getState().reset();
});

describe("ExportStepButton", () => {
  it("is disabled while the analysis holds no filter and no figure", () => {
    useEdaStore.getState().applyAnalysisState(analysis());
    render(<ExportStepButton conversationId="conv-1" />);
    expect(screen.getByRole("button", { name: "Export as step" })).toBeDisabled();
  });

  it("exports the subset when no figure is drawn", async () => {
    let body: unknown = null;
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          analysis: analysis({ revision: 1, numFilters: 1 }),
          step: strategyPayload(),
        });
      }),
    );
    useEdaStore
      .getState()
      .applyAnalysisState(analysis({ numFilters: 1, numComputations: 0 }));
    render(<ExportStepButton conversationId="conv-1" />);
    const button = screen.getByRole("button", { name: "Export as step" });
    expect(button).toBeEnabled();
    await userEvent.click(button);
    await waitFor(() => {
      expect(body).toEqual({ action: "export-step", source: "subset" });
    });
  });

  it("shows why a subset that selects no genes wrote no step", async () => {
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json(
          {
            type: "about:blank",
            title: "The subset selects no genes",
            status: 422,
            detail: SAMPLE_ONLY_REFUSAL,
            code: "VALIDATION_ERROR",
          },
          {
            status: 422,
            headers: { "Content-Type": "application/problem+json" },
          },
        ),
      ),
    );
    useEdaStore
      .getState()
      .applyAnalysisState(analysis({ numFilters: 1, numComputations: 0 }));
    render(<ExportStepButton conversationId="conv-1" />);
    await userEvent.click(screen.getByRole("button", { name: "Export as step" }));
    expect(await screen.findByTestId("eda-export-error")).toHaveTextContent(
      SAMPLE_ONLY_REFUSAL,
    );
    expect(screen.getAllByText(SAMPLE_ONLY_REFUSAL)).toHaveLength(1);
    expect(toastError).not.toHaveBeenCalled();
    expect(screen.queryByTestId("eda-export-began-strategy")).toBe(null);
  });

  it("is disabled and says why when the analysis cannot export rows", () => {
    useEdaStore.getState().applyAnalysisState(analysis({ canExportRows: false }));
    useEdaStore.getState().applyViz(figure());
    render(<ExportStepButton conversationId="conv-1" />);
    expect(screen.getByRole("button", { name: "Export as step" })).toBeDisabled();
    expect(screen.getByTestId("eda-export-blocked")).toHaveTextContent(
      "This study cannot export genes as a step.",
    );
  });

  it("is disabled while a comparison is recorded but its figure is not read", () => {
    useEdaStore.getState().applyAnalysisState(
      analysis({
        compute: {
          method: "DESeq",
          identifierVariable: "Gene",
          valueVariable: "Antisense Count",
          comparatorVariable: "temperature_condition",
          groupA: ["normal"],
          groupB: ["febrile"],
        },
      }),
    );
    render(<ExportStepButton conversationId="conv-1" />);
    expect(screen.getByRole("button", { name: "Export as step" })).toBeDisabled();
  });

  it("exports the volcano and leaves the cut to the analysis the site stores", async () => {
    let body: unknown = null;
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          analysis: analysis({ revision: 1 }),
          step: strategyPayload(),
        });
      }),
    );
    useEdaStore.getState().applyAnalysisState(analysis());
    useEdaStore.getState().applyViz(
      figure({
        effectSizeThreshold: 2,
        significanceThreshold: 0.01,
        effectDirection: "upOnly",
      }),
    );
    render(<ExportStepButton conversationId="conv-1" />);
    await userEvent.click(screen.getByRole("button", { name: "Export as step" }));
    await waitFor(() => {
      expect(body).toEqual({ action: "export-step", source: "volcano" });
    });
  });

  it("writes the returned strategy into the cache the graph already reads", async () => {
    answersWith({
      analysis: analysis({ revision: 1 }),
      step: strategyPayload(),
    });
    const queryClient = createTestQueryClient();
    readyToExport();
    render(
      <QueryClientProvider client={queryClient}>
        <ExportStepButton conversationId="conv-1" />
      </QueryClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Export as step" }));
    await waitFor(() => {
      const cached = queryClient.getQueryData(strategyQueryKey("conv-1")) as {
        steps: { id: string }[];
      };
      expect(cached.steps.map((s) => s.id)).toEqual(["step_eda"]);
    });
  });

  it("marks the step answers of the thread stale when it writes the strategy", async () => {
    answersWith({
      analysis: analysis({ revision: 1 }),
      step: strategyPayload(),
    });
    const queryClient = createTestQueryClient();
    const pageKey = [
      ...getStepRecordsQueryKey("conv-1", "step_a", {
        siteId: "plasmodb",
        offset: 0,
        limit: 50,
      }),
      { wdkStepId: 22 },
    ];
    queryClient.setQueryData(pageKey, { records: [] });
    readyToExport();
    render(
      <QueryClientProvider client={queryClient}>
        <ExportStepButton conversationId="conv-1" />
      </QueryClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Export as step" }));
    await waitFor(() => {
      expect(queryClient.getQueryState(pageKey)?.isInvalidated).toBe(true);
    });
  });

  it("applies the analysis state the export answered with", async () => {
    answersWith({
      analysis: analysis({ revision: 7 }),
      step: strategyPayload(),
    });
    readyToExport();
    render(<ExportStepButton conversationId="conv-1" />);
    await userEvent.click(screen.getByRole("button", { name: "Export as step" }));
    await waitFor(() => {
      expect(useEdaStore.getState().analysis?.revision).toBe(7);
    });
  });

  it("says the export began the strategy when the thread had none", async () => {
    answersWith({
      analysis: analysis({ revision: 1 }),
      step: strategyPayload(),
    });
    readyToExport();
    render(<ExportStepButton conversationId="conv-1" />);
    await userEvent.click(screen.getByRole("button", { name: "Export as step" }));
    expect(await screen.findByTestId("eda-export-began-strategy")).toHaveTextContent(
      "This step is now the strategy's first step.",
    );
    expect(
      screen.getByRole("link", { name: "Open the strategy canvas" }),
    ).toHaveAttribute("href", "/plasmodb/conversation/conv-1/strategy");
    expect(screen.queryByTestId("eda-export-draft-step")).toBe(null);
  });

  it("names the exported step by the genes it keeps", async () => {
    answersWith({
      analysis: analysis({ revision: 1 }),
      step: BESIDE_EXISTING,
    });
    readyToExport();
    render(<ExportStepButton conversationId="conv-1" />);
    await userEvent.click(screen.getByRole("button", { name: "Export as step" }));
    expect(await screen.findByTestId("eda-export-step-name")).toHaveTextContent(
      "Exported: Genes higher in febrile than in normal",
    );
  });

  it("calls the step a draft beside an existing strategy, never pushed", async () => {
    answersWith({
      analysis: analysis({ revision: 1 }),
      step: BESIDE_EXISTING,
    });
    readyToExport();
    render(<ExportStepButton conversationId="conv-1" />);
    await userEvent.click(screen.getByRole("button", { name: "Export as step" }));
    expect(await screen.findByTestId("eda-export-draft-step")).toHaveTextContent(
      "This step is a draft root. It is not part of the pushed strategy until you attach it.",
    );
    expect(
      screen.getByRole("link", { name: "Attach it in the strategy canvas" }),
    ).toHaveAttribute("href", "/plasmodb/conversation/conv-1/strategy");
    expect(screen.queryByTestId("eda-export-began-strategy")).toBe(null);
  });

  it("reports a failed export once, beside the button, and no step", async () => {
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({ detail: "step creation failed" }, { status: 422 }),
      ),
    );
    readyToExport();
    render(<ExportStepButton conversationId="conv-1" />, {
      wrapper: appQueryClientWrapper(),
    });
    await userEvent.click(screen.getByRole("button", { name: "Export as step" }));
    expect(await screen.findByTestId("eda-export-error")).toHaveTextContent(
      "step creation failed",
    );
    expect(screen.getAllByText("step creation failed")).toHaveLength(1);
    expect(toastError).not.toHaveBeenCalled();
    expect(screen.queryByTestId("eda-export-began-strategy")).toBe(null);
  });

  it("reports a strategy payload it cannot read, and still takes the analysis", async () => {
    answersWith({
      analysis: analysis({ revision: 4 }),
      step: { steps: [EDA_STEP] },
    });
    readyToExport();
    render(<ExportStepButton conversationId="conv-1" />);
    await userEvent.click(screen.getByRole("button", { name: "Export as step" }));
    expect(await screen.findByTestId("eda-export-error")).toHaveTextContent(
      "The export answered with a strategy the app cannot read.",
    );
    expect(useEdaStore.getState().analysis?.revision).toBe(4);
  });

  it("says how many genes of the cut the site's annotation lacks", async () => {
    useEdaStore.getState().applyAnalysisState(analysis());
    useEdaStore.getState().applyViz({
      ...figure(),
      totalPoints: 3,
      retainedPoints: 2,
      points: [
        {
          pointId: "PF3D7_0100200",
          effectSize: 3.94,
          pValue: 0.00002,
          adjustedPValue: 0.00014,
          retained: true,
        },
        {
          pointId: "PF3D7_9901100",
          effectSize: -2.5,
          pValue: 0.001,
          adjustedPValue: 0.004,
          retained: true,
        },
        {
          pointId: "PF3D7_0100100",
          effectSize: -0.2,
          pValue: 0.35,
          adjustedPValue: 0.47,
          retained: false,
        },
      ],
    });
    answersWith({
      analysis: null,
      step: strategyPayload({ steps: [{ ...EDA_STEP, estimatedSize: 1 }] }),
    });
    render(<ExportStepButton conversationId="conv-1" />);

    await userEvent.click(screen.getByRole("button", { name: "Export as step" }));

    expect(await screen.findByTestId("eda-export-unmatched")).toHaveTextContent(
      "1 of 2 genes is not a gene of PlasmoDB's current annotation.",
    );
  });

  it("says nothing of unmatched genes when the step holds the whole cut", async () => {
    readyToExport();
    answersWith({ analysis: null, step: strategyPayload() });
    render(<ExportStepButton conversationId="conv-1" />);

    await userEvent.click(screen.getByRole("button", { name: "Export as step" }));

    await screen.findByTestId("eda-export-step-name");
    expect(screen.queryByTestId("eda-export-unmatched")).toBe(null);
  });
});
