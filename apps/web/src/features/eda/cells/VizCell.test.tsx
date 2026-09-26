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
import { act, render, screen, waitFor } from "@testing-library/react";
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

import { useAuthGateStore } from "@/state/useAuthGateStore";
import { useEdaStore } from "@/state/eda";
import { appQueryClientWrapper } from "@/app/components/__fixtures__/appQueryClient";
import { VizCell } from "./VizCell";

const BASE = "http://localhost:3000";
const server = setupServer();

const ANALYSIS = {
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
};

const VOLCANO = {
  datasetId: "DS_e973eadd57",
  analysisId: "a-1",
  chart: "volcano" as const,
  effectSizeLabel: "log2(Fold Change)",
  effectSizeThreshold: 1,
  significanceThreshold: 0.05,
  effectDirection: "upAndDown" as const,
  totalPoints: 5,
  retainedPoints: 3,
  retainedPointIds: ["PF3D7_0100200", "PF3D7_0100300", "PF3D7_0100400"],
  points: [
    {
      pointId: "PF3D7_0100100",
      effectSize: -0.218035922112735,
      pValue: 0.350285751849808,
      adjustedPValue: 0.46960449943855,
      retained: false,
    },
    {
      pointId: "PF3D7_0100200",
      effectSize: 3.94437533216012,
      pValue: 1.95781599815607e-5,
      adjustedPValue: 0.000137772236907279,
      retained: true,
    },
    {
      pointId: "PF3D7_0100300",
      effectSize: -2.5,
      pValue: 0.001,
      adjustedPValue: 0.004,
      retained: true,
    },
    /** Significant on the raw p and not on the adjusted one: WDK cuts on the
     * raw p, so this gene is kept. */
    {
      pointId: "PF3D7_0100400",
      effectSize: 2.2,
      pValue: 0.02,
      adjustedPValue: 0.08,
      retained: true,
    },
    {
      pointId: "PF3D7_MIT04200",
      effectSize: -1.49447459261845,
      pValue: null,
      adjustedPValue: null,
      retained: false,
    },
  ],
};

/** The volcano route's own shape: no dataset or analysis id on the answer. */
function vizResponse(totalPoints: number, overrides: Record<string, unknown> = {}) {
  return {
    chart: "volcano",
    effectSizeLabel: "log2(Fold Change)",
    effectSizeThreshold: 1,
    significanceThreshold: 0.05,
    effectDirection: "upAndDown",
    totalPoints,
    retainedPoints: 3,
    retainedPointIds: VOLCANO.retainedPointIds,
    points: VOLCANO.points,
    comparison: { groupA: ["normal"], groupB: ["febrile"] },
    ...overrides,
  };
}

/** Holds the figure read open, so the cell draws the plot the store already has. */
function holdTheRead(): () => void {
  let release = () => undefined as void;
  const gate = new Promise<void>((resolve) => {
    release = () => {
      resolve();
    };
  });
  server.use(
    http.post(`${BASE}/api/v1/eda/viz`, async () => {
      await gate;
      return HttpResponse.json(vizResponse(5));
    }),
  );
  return release;
}

/** One entry per HTTP request; the interceptor may run a resolver twice. */
function createRequestLog() {
  const seen = new Set<string>();
  return {
    record: (requestId: string) => seen.add(requestId),
    get count() {
      return seen.size;
    },
  };
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
beforeEach(() => {
  toastError.mockClear();
  useEdaStore.getState().reset();
  useEdaStore.getState().applyAnalysisState(ANALYSIS);
});

describe("VizCell reads the figure", () => {
  it("reads the figure when it mounts, and sends no cut", async () => {
    let body: unknown = null;
    let url = "";
    server.use(
      http.post(`${BASE}/api/v1/eda/viz`, async ({ request }) => {
        body = await request.json();
        url = request.url;
        return HttpResponse.json(vizResponse(5));
      }),
    );
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId("eda-viz-volcano")).toHaveAttribute("role", "img");
    expect(body).toEqual({ chart: "volcano" });
    expect(url).toBe(`${BASE}/api/v1/eda/viz?siteId=plasmodb&conversationId=conv-1`);
    expect(screen.getByTestId("eda-volcano-selection")).toHaveTextContent(
      "3 genes selected",
    );
  });

  it("states the cut the analysis stores and offers no control to change it", async () => {
    server.use(
      http.post(`${BASE}/api/v1/eda/viz`, () =>
        HttpResponse.json(
          vizResponse(5, {
            effectSizeThreshold: 2,
            significanceThreshold: 0.01,
            effectDirection: "upOnly",
            retainedPointIds: ["PF3D7_0100200"],
          }),
        ),
      ),
    );
    const { container } = render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId("eda-volcano-cut")).toHaveTextContent(
      "Higher in febrile, |effect size| >= 2, p <= 0.01",
    );
    expect(container.querySelectorAll("input, select, textarea")).toHaveLength(0);
    expect(screen.getByTestId("eda-volcano-selection")).toHaveTextContent(
      "1 gene selected",
    );
  });

  it("names both groups of the comparison under the cell title", async () => {
    server.use(
      http.post(`${BASE}/api/v1/eda/viz`, () =>
        HttpResponse.json(
          vizResponse(5, {
            comparison: { groupA: ["24h pbm"], groupB: ["18h pbm", "36h pbm"] },
          }),
        ),
      ),
    );
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    await screen.findByTestId("eda-viz-volcano");
    expect(screen.getByTestId("eda-viz-cell")).toHaveTextContent(
      "Group A: 24h pbm - Group B: 18h pbm, 36h pbm",
    );
    expect(screen.getByTestId("eda-viz-volcano")).toHaveAttribute(
      "aria-label",
      "Volcano plot, Higher in 18h pbm, 36h pbm (2) and Higher in 24h pbm (1)",
    );
  });

  it("reads the figure again when the analysis moves to a new revision", async () => {
    const log = createRequestLog();
    let served = 0;
    server.use(
      http.post(`${BASE}/api/v1/eda/viz`, ({ requestId }) => {
        log.record(requestId);
        served += 1;
        return HttpResponse.json(vizResponse(served === 1 ? 5 : 77));
      }),
    );
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    await screen.findByTestId("eda-viz-volcano");
    expect(screen.getByTestId("eda-volcano-selection")).toHaveTextContent(
      "3 of 5 retained by the comparison",
    );

    act(() => {
      useEdaStore.getState().applyAnalysisState({ ...ANALYSIS, revision: 1 });
    });
    await waitFor(() => {
      expect(screen.getByTestId("eda-volcano-selection")).toHaveTextContent(
        "3 of 77 retained by the comparison",
      );
    });
    expect(log.count).toBe(2);
  });

  it("shows a spinner while the figure read is in flight", async () => {
    const release = holdTheRead();
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId("eda-viz-loading")).toBeInTheDocument();
    release();
    expect(await screen.findByTestId("eda-viz-volcano")).toHaveAttribute("role", "img");
    expect(screen.queryByTestId("eda-viz-loading")).toBe(null);
  });

  it("names a failed figure read once, beside the plot and in no toast", async () => {
    server.use(
      http.post(`${BASE}/api/v1/eda/viz`, () =>
        HttpResponse.json(
          { detail: "Compute results are not available for the requested job." },
          { status: 400 },
        ),
      ),
    );
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />, {
      wrapper: appQueryClientWrapper(),
    });
    expect(await screen.findByTestId("eda-viz-error")).toHaveTextContent(
      "Compute results are not available for the requested job.",
    );
    expect(
      screen.getAllByText("Compute results are not available for the requested job."),
    ).toHaveLength(1);
    expect(toastError).not.toHaveBeenCalled();
  });

  it("asks for a VEuPathDB sign-in when the figure read is refused for a missing login", async () => {
    const detail =
      "VEuPathDB serves registered users only, and this request carried no registered VEuPathDB token.";
    server.use(
      http.post(`${BASE}/api/v1/eda/viz`, () =>
        HttpResponse.json(
          {
            title: "VEuPathDB login required",
            status: 401,
            detail,
            code: "WDK_LOGIN_REQUIRED",
          },
          { status: 401 },
        ),
      ),
    );
    useAuthGateStore.getState().dismissSignIn();
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />, {
      wrapper: appQueryClientWrapper(),
    });
    expect(await screen.findByTestId("eda-viz-error")).toHaveTextContent(detail);
    expect(useAuthGateStore.getState().signInRequired).toBe(true);
    expect(useAuthGateStore.getState().signInReason).toBe(detail);
    expect(toastError.mock.calls).toEqual([[detail]]);
  });
});

describe("VizCell draws the plot the store holds", () => {
  let release: () => void = () => undefined;
  beforeEach(() => {
    release = holdTheRead();
  });
  afterEach(() => {
    release();
  });

  it("renders the volcano from a viz payload in the store", () => {
    useEdaStore.getState().applyViz(VOLCANO);
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(screen.getByTestId("eda-viz-volcano")).toHaveAttribute("role", "img");
  });

  it("prints no comparison for a plot that names none", () => {
    useEdaStore.getState().applyViz(VOLCANO);
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(screen.getByTestId("eda-viz-cell")).not.toHaveTextContent("Group A:");
  });

  it("counts the selected genes and agrees with the retained total", () => {
    useEdaStore.getState().applyViz(VOLCANO);
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(screen.getByTestId("eda-volcano-selection")).toHaveTextContent(
      "3 genes selected, 3 of 5 retained by the comparison",
    );
  });

  it("cuts on the raw p-value, as WDK's step does", () => {
    useEdaStore.getState().applyViz(VOLCANO);
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(screen.getByTestId("eda-volcano-gene-PF3D7_0100400")).toHaveTextContent(
      "PF3D7_01004002.202.00e-2",
    );
  });

  it("reads out every retained gene, in the service's order, with its effect size and p-value", () => {
    useEdaStore.getState().applyViz(VOLCANO);
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    const rows = screen.getAllByTestId(/^eda-volcano-gene-/);
    expect(rows.map((row) => row.textContent)).toEqual([
      "PF3D7_01002003.941.96e-5",
      "PF3D7_0100300-2.501.00e-3",
      "PF3D7_01004002.202.00e-2",
    ]);
  });

  it("caps the read-out list and says how many genes it holds back", () => {
    const points = Array.from({ length: 60 }, (_, index) => ({
      pointId: `PF3D7_${String(index).padStart(6, "0")}`,
      effectSize: 2 + index,
      pValue: 1e-6,
      adjustedPValue: 1e-6,
      retained: true,
    }));
    useEdaStore.getState().applyViz({
      ...VOLCANO,
      points,
      totalPoints: 60,
      retainedPoints: 60,
      retainedPointIds: points.map((point) => point.pointId),
    });
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(screen.getAllByTestId(/^eda-volcano-gene-/)).toHaveLength(50);
    expect(screen.getByTestId("eda-volcano-readout-cap")).toHaveTextContent(
      "The first 50 of 60 selected genes are listed.",
    );
  });

  it("reports the point it could not plot", () => {
    useEdaStore.getState().applyViz(VOLCANO);
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(screen.getByTestId("eda-viz-volcano-dropped")).toHaveTextContent(
      "1 point without a p-value was not plotted",
    );
  });

  it("draws a scatter for chart scatter", () => {
    useEdaStore.getState().applyViz({ ...VOLCANO, chart: "scatter" });
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(screen.getByTestId("eda-viz-scatter")).toHaveAttribute("role", "img");
  });

  it("tables every plotted scatter point beside the chart", () => {
    useEdaStore.getState().applyViz({ ...VOLCANO, chart: "scatter" });
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    const rows = screen.getAllByTestId(/^eda-viz-scatter-row-/);
    expect(rows.map((row) => row.getAttribute("data-testid"))).toEqual([
      "eda-viz-scatter-row-PF3D7_0100100",
      "eda-viz-scatter-row-PF3D7_0100200",
      "eda-viz-scatter-row-PF3D7_0100300",
      "eda-viz-scatter-row-PF3D7_0100400",
    ]);
    expect(rows[1]).toHaveTextContent("3.94");
    expect(rows[1]).toHaveTextContent("4.71");
  });

  it("reports the scatter point it could not plot", () => {
    useEdaStore.getState().applyViz({ ...VOLCANO, chart: "scatter" });
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(screen.getByTestId("eda-viz-scatter-no-pvalue")).toHaveTextContent(
      "1 point without a p-value was not plotted",
    );
  });

  it("caps the scatter table the same way", () => {
    const points = Array.from({ length: 60 }, (_, index) => ({
      pointId: `PF3D7_${String(index).padStart(6, "0")}`,
      effectSize: 2 + index,
      pValue: 1e-6,
      adjustedPValue: 1e-6,
      retained: true,
    }));
    useEdaStore.getState().applyViz({ ...VOLCANO, chart: "scatter", points });
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(screen.getAllByTestId(/^eda-viz-scatter-row-/)).toHaveLength(50);
    expect(screen.getByTestId("eda-viz-scatter-cap")).toHaveTextContent(
      "The first 50 of 60 plotted points are listed.",
    );
  });

  it("says a bar chart cannot be drawn from a point cloud", () => {
    useEdaStore.getState().applyViz({ ...VOLCANO, chart: "bar" });
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(screen.getByTestId("eda-viz-unsupported-chart")).toHaveTextContent(
      "bar plots are not available from this comparison",
    );
  });

  it("says the same for a histogram and a boxplot", async () => {
    useEdaStore.getState().applyViz({ ...VOLCANO, chart: "histogram" });
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(screen.getByTestId("eda-viz-unsupported-chart")).toHaveTextContent(
      "histogram plots are not available from this comparison",
    );
    useEdaStore.getState().applyViz({ ...VOLCANO, chart: "boxplot" });
    await waitFor(() => {
      expect(screen.getByTestId("eda-viz-unsupported-chart")).toHaveTextContent(
        "boxplot plots are not available from this comparison",
      );
    });
  });
});
