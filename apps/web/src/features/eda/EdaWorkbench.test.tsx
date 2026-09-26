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
import {
  appQueryClientWrapper,
  appTestQueryClient,
} from "@/app/components/__fixtures__/appQueryClient";
import { EdaWorkbench } from "./EdaWorkbench";

const BASE = "http://localhost:3000";
const server = setupServer();

/** The site's own analysis page, as `services/eda/urls.py` builds it. */
const ANALYSIS_URL =
  "https://plasmodb.org/plasmo/app/workspace/analyses/DS_e973eadd57/a-1";

const COMPUTE = {
  method: "DESeq",
  identifierVariable: "Gene",
  valueVariable: "Antisense Count",
  comparatorVariable: "temperature_condition",
  groupA: ["normal"],
  groupB: ["febrile"],
};

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
  analysisUrl: ANALYSIS_URL,
  compute: null,
};

const FEBRILE = {
  entityId: "ENT_8151325d",
  variableId: "VAR_081ab087",
  type: "stringSet",
  stringSet: ["febrile"],
};

const FILTERED = {
  ...ANALYSIS,
  numFilters: 1,
  filters: [FEBRILE],
  filterSummaries: ["temperature_condition is febrile"],
  entityCounts: [
    {
      entityId: "ENT_8151325d",
      entityDisplayName: "Sample",
      count: 6,
      unfilteredCount: 12,
    },
  ],
};

const COMPARED = { ...FILTERED, numComputations: 1, compute: COMPUTE };

const VOLCANO = {
  chart: "volcano",
  effectSizeLabel: "log2(Fold Change)",
  effectSizeThreshold: 1,
  significanceThreshold: 0.05,
  effectDirection: "upAndDown",
  totalPoints: 2,
  retainedPoints: 1,
  retainedPointIds: ["PF3D7_0100200"],
  points: [
    {
      pointId: "PF3D7_0100100",
      effectSize: -0.21,
      pValue: 0.35,
      adjustedPValue: 0.46,
      retained: false,
    },
    {
      pointId: "PF3D7_0100200",
      effectSize: 3.94,
      pValue: 1.9e-5,
      adjustedPValue: 1.3e-4,
      retained: true,
    },
  ],
  comparison: { groupA: ["normal"], groupB: ["febrile"] },
};

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
beforeEach(() => {
  toastError.mockClear();
  useEdaStore.getState().reset();
});

function reads(analysis: object | null) {
  server.use(
    http.get(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
      HttpResponse.json({ analysis }),
    ),
  );
}

function volcano() {
  server.use(http.post(`${BASE}/api/v1/eda/viz`, () => HttpResponse.json(VOLCANO)));
}

function unbound() {
  reads(null);
  server.use(
    http.get(`${BASE}/api/v1/eda/datasets`, () => HttpResponse.json({ datasets: [] })),
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
    http.get(`${BASE}/api/v1/eda/datasets`, () => HttpResponse.json({ datasets: [] })),
  );
}

describe("EdaWorkbench", () => {
  it("shows the study picker and no analysis when nothing is bound", async () => {
    unbound();
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId("eda-study-picker")).toBeInTheDocument();
    expect(screen.queryByTestId("eda-subset-summary")).toBe(null);
    expect(screen.getByTestId("eda-workbench-header")).toHaveTextContent(
      "No study selected",
    );
  });

  it("hydrates from the binding endpoint and shows the subset it holds", async () => {
    reads(FILTERED);
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    const subset = await screen.findByTestId("eda-subset-summary");
    await waitFor(() => {
      expect(useEdaStore.getState().binding?.analysisId).toBe("a-1");
    });
    expect(within(subset).getByTestId("eda-filter-chip-0")).toHaveTextContent(
      "temperature_condition is febrile",
    );
    expect(
      within(subset).getByTestId("eda-entity-count-ENT_8151325d"),
    ).toHaveTextContent("6 of 12 Sample");
    expect(screen.queryByTestId("eda-study-picker")).toBe(null);
  });

  it("says the subset is the whole study when the analysis holds no filter", async () => {
    reads(ANALYSIS);
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId("eda-subset-no-filters")).toHaveTextContent(
      "No filters: the subset is the whole study.",
    );
  });

  it("counts a filter the analysis holds but no sentence names", async () => {
    reads({ ...FILTERED, numFilters: 3 });
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId("eda-subset-filter-overflow")).toHaveTextContent(
      "2 more filters",
    );
  });

  it("states the comparison as a sentence, with every variable by its name", async () => {
    reads(COMPARED);
    volcano();
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId("eda-comparison-sentence")).toHaveTextContent(
      "DESeq compares normal (group A) with febrile (group B) on temperature_condition, reading Antisense Count per Gene.",
    );
  });

  it("says no comparison has run, and where to ask for one", async () => {
    reads(FILTERED);
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId("eda-comparison-none")).toHaveTextContent(
      "No comparison has run on this analysis. Ask for one in the conversation.",
    );
    expect(screen.queryByTestId("eda-viz-cell")).toBe(null);
  });

  it("draws the figure of the comparison the analysis holds", async () => {
    reads(COMPARED);
    volcano();
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId("eda-viz-volcano")).toHaveAttribute("role", "img");
    expect(screen.getByTestId("eda-volcano-selection")).toHaveTextContent(
      "1 gene selected, 1 of 2 retained by the comparison",
    );
  });

  it("renders no form control, only the study's own link and the two actions", async () => {
    reads(COMPARED);
    volcano();
    const { container } = render(
      <EdaWorkbench siteId="plasmodb" conversationId="conv-1" />,
    );
    await screen.findByTestId("eda-viz-volcano");
    expect(container.querySelectorAll("input, select, textarea")).toHaveLength(0);
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
    expect(screen.queryAllByRole("combobox")).toHaveLength(0);
    expect(screen.getAllByRole("button").map((button) => button.textContent)).toEqual([
      "Change study",
      "Export as step",
    ]);
    expect(screen.getAllByRole("link").map((link) => link.textContent)).toEqual([
      "Back to conversation",
      "Open in PlasmoDB",
    ]);
  });

  it("opens the recorded analysis on the site's own page, in a new tab", async () => {
    reads(ANALYSIS);
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    const link = await screen.findByRole("link", { name: "Open in PlasmoDB" });
    expect(link).toHaveAttribute(
      "href",
      "https://plasmodb.org/plasmo/app/workspace/analyses/DS_e973eadd57/a-1",
    );
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
    expect(
      within(screen.getByTestId("eda-workbench-header")).getByRole("link", {
        name: "Open in PlasmoDB",
      }),
    ).toBe(link);
  });

  it("says beside the site link that the analysis is edited on the site", async () => {
    reads(ANALYSIS);
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    await screen.findByRole("link", { name: "Open in PlasmoDB" });
    expect(
      within(screen.getByTestId("eda-workbench-header")).getByText(
        "Edit on PlasmoDB; this tab shows what the site holds.",
      ),
    ).toBeInTheDocument();
  });

  it("reads the analysis from the site again each time the tab opens", async () => {
    const client = appTestQueryClient();
    reads(FILTERED);
    const first = render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />, {
      wrapper: appQueryClientWrapper(client),
    });
    expect(await screen.findByTestId("eda-filter-chip-0")).toHaveTextContent(
      "temperature_condition is febrile",
    );
    first.unmount();

    reads({
      ...FILTERED,
      filterSummaries: ["temperature_condition is normal"],
      entityCounts: [
        {
          entityId: "ENT_8151325d",
          entityDisplayName: "Sample",
          count: 3,
          unfilteredCount: 12,
        },
      ],
    });
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />, {
      wrapper: appQueryClientWrapper(client),
    });
    await waitFor(() => {
      expect(screen.getByTestId("eda-filter-chip-0")).toHaveTextContent(
        "temperature_condition is normal",
      );
    });
    expect(screen.getByTestId("eda-entity-count-ENT_8151325d")).toHaveTextContent(
      "3 of 12 Sample",
    );
  });

  it("reads the figure from the site again each time the tab opens", async () => {
    const client = appTestQueryClient();
    let served = 0;
    reads(COMPARED);
    server.use(
      http.post(`${BASE}/api/v1/eda/viz`, () => {
        served += 1;
        return HttpResponse.json(
          served === 1 ? VOLCANO : { ...VOLCANO, totalPoints: 77, retainedPoints: 9 },
        );
      }),
    );
    const first = render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />, {
      wrapper: appQueryClientWrapper(client),
    });
    expect(await screen.findByTestId("eda-volcano-selection")).toHaveTextContent(
      "1 of 2 retained by the comparison",
    );
    first.unmount();

    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />, {
      wrapper: appQueryClientWrapper(client),
    });
    await waitFor(() => {
      expect(screen.getByTestId("eda-volcano-selection")).toHaveTextContent(
        "9 of 77 retained by the comparison",
      );
    });
  });

  it("puts the study title in the header title and the analysis name in the subtitle", async () => {
    reads(ANALYSIS);
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
    reads({ ...ANALYSIS, displayName: ANALYSIS.studyDisplayName });
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
    reads(ANALYSIS);
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, async ({ request }) => {
        patchBody = await request.clone().json();
        return HttpResponse.json({ analysis: null, step: null });
      }),
      http.get(`${BASE}/api/v1/eda/datasets`, () =>
        HttpResponse.json({ datasets: [] }),
      ),
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
    reads(ANALYSIS);
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
    expect(screen.getByTestId("eda-subset-summary")).toBeInTheDocument();
    expect(useEdaStore.getState().binding?.analysisId).toBe("a-1");
  });

  it("reports a failed binding read once, rather than showing the picker", async () => {
    server.use(
      http.get(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({ detail: "binding read failed" }, { status: 500 }),
      ),
    );
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />, {
      wrapper: appQueryClientWrapper(),
    });
    expect(await screen.findByTestId("eda-binding-error")).toHaveTextContent(
      "binding read failed",
    );
    expect(screen.queryByTestId("eda-study-picker")).toBe(null);
    expect(screen.getAllByText("binding read failed")).toHaveLength(1);
    expect(toastError).not.toHaveBeenCalled();
  });

  it("puts the export button in the header, disabled before any compute or filter", async () => {
    reads(ANALYSIS);
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    await screen.findByTestId("eda-subset-summary");
    const header = screen.getByTestId("eda-workbench-header");
    expect(
      within(header).getByRole("button", { name: "Export as step" }),
    ).toBeDisabled();
    expect(within(header).getByRole("button", { name: "Change study" })).toBeEnabled();
  });

  it("offers no export button while nothing is bound", async () => {
    unbound();
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    await screen.findByTestId("eda-study-picker");
    expect(screen.queryByRole("button", { name: "Export as step" })).toBe(null);
  });

  it("drops the previous analysis's subset when the conversation switches analysis", async () => {
    reads(FILTERED);
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId("eda-filter-chip-0")).toBeInTheDocument();

    act(() => {
      useEdaStore.getState().applyAnalysisState({
        ...ANALYSIS,
        analysisId: "a-2",
        displayName: "Whole study",
      });
    });

    await waitFor(() => {
      expect(screen.getByTestId("eda-entity-count-ENT_8151325d")).toHaveTextContent(
        "12 of 12 Sample",
      );
    });
    expect(screen.queryByTestId("eda-filter-chip-0")).toBe(null);
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
        return HttpResponse.json({ analysis: null, step: null });
      }),
    );
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    const failure = await screen.findByTestId("eda-binding-error");
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
    reads(ANALYSIS);
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    const back = await screen.findByRole("link", { name: "Back to conversation" });
    expect(back).toHaveAttribute("href", "/plasmodb/conversation/conv-1");
  });

  it("links back to the conversation while no study is open", async () => {
    unbound();
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    await screen.findByTestId("eda-study-picker");
    expect(screen.getByRole("link", { name: "Back to conversation" })).toHaveAttribute(
      "href",
      "/plasmodb/conversation/conv-1",
    );
  });

  it("offers no Change study button and no site link while nothing is bound", async () => {
    unbound();
    render(<EdaWorkbench siteId="plasmodb" conversationId="conv-1" />);
    await screen.findByTestId("eda-study-picker");
    expect(screen.queryByRole("button", { name: "Change study" })).toBe(null);
    expect(screen.queryByRole("link", { name: "Open in PlasmoDB" })).toBe(null);
  });
});
