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
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

vi.mock("@/lib/components/charts/echartsRegistry", () => ({
  initChart: () => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    isDisposed: () => false,
  }),
}));

const toastError = vi.fn();
vi.mock("sonner", () => ({ toast: { error: (m: string) => toastError(m) } }));

import { useEdaStore } from "@/state/eda";
import { EdaWorkbench } from "./EdaWorkbench";

const BASE = "http://localhost:3000";
const server = setupServer();

const ANALYSIS = {
  siteId: "plasmodb",
  datasetId: "DS_e973eadd57",
  studyId: "STUDY_e973eadd57",
  analysisId: "a-1",
  revision: 0,
  studyDisplayName: "Heat shock response in sensitive mutants (LRR5, DHC)",
  displayName: "Febrile samples",
  numFilters: 0,
  numComputations: 0,
  filters: [],
  filterSummaries: [],
  entityCounts: [
    {
      entityId: "ENT_8151325d",
      entityDisplayName: "Sample",
      count: 12,
      unfilteredCount: 12,
    },
  ],
  canExportRows: true,
};

const STUDY_DETAIL = {
  datasetId: "DS_e973eadd57",
  studyId: "STUDY_e973eadd57",
  displayName: ANALYSIS.studyDisplayName,
  entities: [
    {
      entityId: "ENT_8151325d",
      displayName: "Sample",
      displayNamePlural: "Samples",
      parentEntityId: null,
      variableCount: 0,
      hasGeneId: false,
    },
  ],
  variables: [],
  geneEntityId: "ENT_8151325d",
  geneEntityProblem: null,
  canSubset: true,
  canExportRows: true,
};

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
beforeEach(() => {
  toastError.mockClear();
  useEdaStore.getState().reset();
  server.use(
    http.get(`${BASE}/api/v1/eda/studies/DS_e973eadd57`, () =>
      HttpResponse.json(STUDY_DETAIL),
    ),
  );
});

function bound() {
  server.use(
    http.get(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
      HttpResponse.json({ analysis: ANALYSIS, descriptor: null }),
    ),
  );
}

const REJECTED_DETAIL =
  "Filter stringSet on variable VAR_035294d0 of entity GENE_PHENOTYPE_DATA_ENTITY names P. vivax, which the vocabulary does not carry. The vocabulary is P. berghei, P. falciparum, P. yoelii. An unknown value returns count 0 rather than an error.";

function rejected() {
  server.use(
    http.get(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
      HttpResponse.json(
        {
          type: "about:blank",
          title: "Subset rejected",
          status: 422,
          detail: REJECTED_DETAIL,
          code: "VALIDATION_ERROR",
        },
        { status: 422, headers: { "content-type": "application/problem+json" } },
      ),
    ),
  );
}

describe("EdaWorkbench", () => {
  it("shows the study picker and no subset cell when nothing is bound", async () => {
    server.use(
      http.get(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({ analysis: null, descriptor: null }),
      ),
    );
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId("eda-study-picker")).toBeInTheDocument();
    expect(screen.queryByTestId("eda-subset-cell")).toBe(null);
    expect(screen.getByTestId("eda-workbench-header")).toHaveTextContent(
      "No study selected",
    );
  });

  it("hydrates from the binding endpoint and mounts the subset cell", async () => {
    bound();
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId("eda-subset-cell")).toBeInTheDocument();
    await waitFor(() => {
      expect(useEdaStore.getState().binding?.analysisId).toBe("a-1");
    });
    expect(screen.queryByTestId("eda-study-picker")).toBe(null);
  });

  it("puts the study title in the header title and the analysis name in the subtitle", async () => {
    bound();
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    const title = await screen.findByTestId("eda-workbench-title");
    await waitFor(() => {
      expect(title.textContent).toBe(
        "Heat shock response in sensitive mutants (LRR5, DHC)",
      );
    });
    expect(screen.getByTestId("eda-workbench-subtitle").textContent).toBe(
      "Febrile samples",
    );
  });

  it("prints no subtitle when the analysis carries the study's own name", async () => {
    server.use(
      http.get(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({
          analysis: { ...ANALYSIS, displayName: ANALYSIS.studyDisplayName },
          descriptor: null,
        }),
      ),
    );
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    const title = await screen.findByTestId("eda-workbench-title");
    await waitFor(() => {
      expect(title.textContent).toBe(
        "Heat shock response in sensitive mutants (LRR5, DHC)",
      );
    });
    expect(screen.queryByTestId("eda-workbench-subtitle")).toBe(null);
  });

  it("unbinds upstream before it clears the store", async () => {
    let patchBody: unknown = null;
    bound();
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, async ({ request }) => {
        patchBody = await request.clone().json();
        return HttpResponse.json({ analysis: null, job: null, step: null });
      }),
    );
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Change study" }));
    await waitFor(() => {
      expect(useEdaStore.getState().binding).toBe(null);
    });
    expect(patchBody).toEqual({ action: "unbind" });
    expect(await screen.findByTestId("eda-study-picker")).toBeInTheDocument();
  });

  it("keeps the binding when unbinding fails, so the tab matches the server", async () => {
    bound();
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({ detail: "unbind failed" }, { status: 500 }),
      ),
    );
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Change study" }));
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith("unbind failed");
    });
    expect(screen.getByTestId("eda-subset-cell")).toBeInTheDocument();
    expect(useEdaStore.getState().binding?.analysisId).toBe("a-1");
  });

  it("reports a failed binding read rather than showing the picker", async () => {
    server.use(
      http.get(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({ detail: "binding read failed" }, { status: 500 }),
      ),
    );
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId("eda-binding-error")).toHaveTextContent(
      "binding read failed",
    );
    expect(screen.queryByTestId("eda-study-picker")).toBe(null);
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith("binding read failed");
    });
  });

  it("mounts the subset, compute and viz cells for a bound analysis", async () => {
    bound();
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId("eda-subset-cell")).toBeInTheDocument();
    expect(screen.getByTestId("eda-compute-cell")).toBeInTheDocument();
    expect(screen.getByTestId("eda-viz-cell")).toBeInTheDocument();
    expect(screen.getByTestId("eda-viz-unavailable")).toHaveTextContent(
      "Run a compute to see its plots.",
    );
  });

  it("puts the export button in the header, disabled before any compute", async () => {
    bound();
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    await screen.findByTestId("eda-subset-cell");
    const header = screen.getByTestId("eda-workbench-header");
    const exportButton = within(header).getByRole("button", {
      name: "Export as step",
    });
    expect(exportButton).toBeDisabled();
    expect(within(header).getByRole("button", { name: "Change study" })).toBeEnabled();
  });

  it("offers no export button while nothing is bound", async () => {
    server.use(
      http.get(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({ analysis: null, descriptor: null }),
      ),
    );
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    await screen.findByTestId("eda-study-picker");
    expect(screen.queryByRole("button", { name: "Export as step" })).toBe(null);
  });

  it("drops the previous analysis's live counts when the thread switches analysis", async () => {
    const SAMPLE = "ENT_8151325d";
    const TEMPERATURE = "VAR_081ab087";
    bound();
    server.use(
      http.get(`${BASE}/api/v1/eda/studies/DS_e973eadd57`, () =>
        HttpResponse.json({
          ...STUDY_DETAIL,
          entities: [{ ...STUDY_DETAIL.entities[0], variableCount: 1 }],
          variables: [
            {
              entityId: SAMPLE,
              variableId: TEMPERATURE,
              displayName: "temperature_condition",
              variableType: "string",
              filterType: "stringSet",
              dataShape: "categorical",
              isMultiValued: false,
              vocabulary: ["febrile", "normal"],
              vocabularyTotal: 2,
              vocabularyNote: null,
              rangeMin: null,
              rangeMax: null,
              dateMin: null,
              dateMax: null,
              subFilterVariableIds: [],
              hideFrom: [],
            },
          ],
        }),
      ),
      http.post(`${BASE}/api/v1/eda/count`, () =>
        HttpResponse.json({ entityId: SAMPLE, count: 6, unfilteredCount: 12 }),
      ),
      http.post(`${BASE}/api/v1/eda/distribution`, () =>
        HttpResponse.json({
          variableId: TEMPERATURE,
          variableDisplayName: "temperature_condition",
          labels: ["febrile"],
          values: [6],
          subsetSize: 6,
          numVarValues: 6,
          numMissingCases: 0,
          isMultiValued: false,
        }),
      ),
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({
          analysis: {
            ...ANALYSIS,
            revision: 1,
            numFilters: 1,
            filters: [
              {
                entityId: SAMPLE,
                variableId: TEMPERATURE,
                type: "stringSet",
                stringSet: ["febrile"],
              },
            ],
            filterSummaries: ["temperature_condition is febrile"],
            entityCounts: [
              {
                entityId: SAMPLE,
                entityDisplayName: "Sample",
                count: 6,
                unfilteredCount: 12,
              },
            ],
          },
          job: null,
          step: null,
        }),
      ),
    );

    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.click(await screen.findByTestId(`eda-variable-${TEMPERATURE}`));
    await userEvent.click(await screen.findByRole("checkbox", { name: "febrile" }));
    await userEvent.click(screen.getByRole("button", { name: "Apply filter" }));
    await waitFor(() => {
      expect(screen.getByTestId(`eda-entity-${SAMPLE}`)).toHaveTextContent("6 of 12");
    });

    act(() => {
      useEdaStore.getState().applyAnalysisState({
        ...ANALYSIS,
        analysisId: "a-2",
        revision: 0,
        displayName: "Whole study",
        entityCounts: [
          {
            entityId: SAMPLE,
            entityDisplayName: "Sample",
            count: 12,
            unfilteredCount: 12,
          },
        ],
      });
    });

    await waitFor(() => {
      expect(screen.getByTestId(`eda-entity-${SAMPLE}`)).toHaveTextContent("12 of 12");
    });
    expect(screen.getByTestId(`eda-entity-${SAMPLE}`)).not.toHaveTextContent("6 of 12");
    expect(screen.queryByTestId(`eda-filter-chip-${SAMPLE}-${TEMPERATURE}`)).toBe(null);
    expect(screen.getByTestId("eda-workbench-subtitle").textContent).toBe(
      "Whole study",
    );
  });

  it("names the rejected filter and leaves the analysis for a different study", async () => {
    let patchBody: unknown = null;
    rejected();
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, async ({ request }) => {
        patchBody = await request.clone().json();
        return HttpResponse.json({ analysis: null, job: null, step: null });
      }),
    );
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    const failure = await screen.findByTestId("eda-binding-error");
    expect(failure).toHaveTextContent("P. vivax");
    expect(failure.textContent).toContain(REJECTED_DETAIL);

    await userEvent.click(
      within(failure).getByRole("button", { name: "Open a different study" }),
    );
    expect(await screen.findByTestId("eda-study-picker")).toBeInTheDocument();
    expect(patchBody).toEqual({ action: "unbind" });
    expect(useEdaStore.getState().binding).toBe(null);
    expect(screen.queryByTestId("eda-binding-error")).toBe(null);
  });

  it("keeps the rejected-subset error on screen when the unbind fails", async () => {
    rejected();
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({ detail: "unbind failed" }, { status: 500 }),
      ),
    );
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    const failure = await screen.findByTestId("eda-binding-error");
    await userEvent.click(
      within(failure).getByRole("button", { name: "Open a different study" }),
    );
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith("unbind failed");
    });
    expect(screen.getByTestId("eda-binding-error")).toHaveTextContent("P. vivax");
    expect(screen.queryByTestId("eda-study-picker")).toBe(null);
    expect(toastError.mock.calls.filter((call) => call[0] === "unbind failed")).toEqual(
      [["unbind failed"]],
    );
  });

  it("links back to the conversation the study belongs to", async () => {
    bound();
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    const back = await screen.findByRole("link", { name: "Back to chat" });
    expect(back).toHaveAttribute("href", "/plasmodb/conversation/conv-1");
  });

  it("links back to the conversation while no study is open", async () => {
    server.use(
      http.get(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({ analysis: null, descriptor: null }),
      ),
    );
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    await screen.findByTestId("eda-study-picker");
    expect(screen.getByRole("link", { name: "Back to chat" })).toHaveAttribute(
      "href",
      "/plasmodb/conversation/conv-1",
    );
  });

  it("opens the analysis in the site's own explorer, in a new tab", async () => {
    server.use(
      http.get(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({
          analysis: {
            ...ANALYSIS,
            analysisUrl:
              "https://plasmodb.org/plasmo/app/workspace/analyses/DS_e973eadd57/a-1",
          },
          descriptor: null,
        }),
      ),
    );
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    const link = await screen.findByRole("link", { name: "Open in PlasmoDB" });
    expect(link).toHaveAttribute(
      "href",
      "https://plasmodb.org/plasmo/app/workspace/analyses/DS_e973eadd57/a-1",
    );
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
  });

  it("offers no site link for an analysis that names no page", async () => {
    bound();
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    await screen.findByTestId("eda-workbench-title");
    expect(screen.queryByRole("link", { name: "Open in PlasmoDB" })).toBe(null);
  });

  it("offers no Change study button while nothing is bound", async () => {
    server.use(
      http.get(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({ analysis: null, descriptor: null }),
      ),
    );
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    await screen.findByTestId("eda-study-picker");
    expect(screen.queryByRole("button", { name: "Change study" })).toBe(null);
  });
});
