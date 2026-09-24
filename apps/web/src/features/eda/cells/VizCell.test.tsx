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
const JOB_ID = "db04204e5386396e1ca2cb78469ab6fb";

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
  retainedPoints: 2,
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
    /** Significant on the raw p, not on the adjusted one: the cut reads the
     * adjusted field, so this gene stays out. */
    {
      pointId: "PF3D7_0100400",
      effectSize: 2.2,
      pValue: 0.02,
      adjustedPValue: 0.08,
      retained: false,
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

const COMPLETED_JOB = {
  jobId: JOB_ID,
  taskId: null,
  appName: "differentialexpression",
  status: "complete",
};

const SECOND_JOB_ID = "8c1f0c0f3d5b4a2e9b7d6c5a4f3e2d1c";

/** The volcano route's own shape: no dataset or analysis id on the answer. */
function vizResponse(totalPoints: number) {
  return {
    chart: "volcano",
    effectSizeLabel: "log2(Fold Change)",
    effectSizeThreshold: 1,
    significanceThreshold: 0.05,
    effectDirection: "upAndDown",
    totalPoints,
    retainedPoints: 2,
    points: VOLCANO.points,
    comparison: { groupA: ["normal"], groupB: ["febrile"] },
  };
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

describe("VizCell", () => {
  it("says why there is nothing to plot before a compute completes", () => {
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(screen.getByTestId("eda-viz-unavailable")).toHaveTextContent(
      "Run a compute to see its plots.",
    );
  });

  it("renders the volcano from a viz payload in the store", () => {
    useEdaStore.getState().applyViz(VOLCANO);
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(screen.getByTestId("eda-viz-volcano")).toHaveAttribute("role", "img");
  });

  it("names both groups of the comparison under the cell title", () => {
    useEdaStore.getState().applyViz({
      ...VOLCANO,
      comparison: { groupA: ["24h pbm"], groupB: ["18h pbm", "36h pbm"] },
    });
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(screen.getByTestId("eda-viz-cell")).toHaveTextContent(
      "Group A: 24h pbm - Group B: 18h pbm, 36h pbm",
    );
  });

  it("names each direction choice by the group whose genes it keeps", () => {
    useEdaStore.getState().applyViz({
      ...VOLCANO,
      comparison: { groupA: ["24h pbm"], groupB: ["18h pbm", "36h pbm"] },
    });
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(
      screen.getByRole("option", { name: "Higher in 18h pbm, 36h pbm" }),
    ).toHaveAttribute("value", "upOnly");
    expect(screen.getByRole("option", { name: "Higher in 24h pbm" })).toHaveAttribute(
      "value",
      "downOnly",
    );
    expect(screen.getByTestId("eda-viz-volcano")).toHaveAttribute(
      "aria-label",
      "Volcano plot, Higher in 18h pbm, 36h pbm (1) and Higher in 24h pbm (1)",
    );
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
      "2 genes selected",
    );
    expect(screen.getByTestId("eda-volcano-selection")).toHaveTextContent(
      "2 of 5 retained by the compute",
    );
  });

  it("cuts on the adjusted p-value, not the raw one", () => {
    useEdaStore.getState().applyViz(VOLCANO);
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(screen.queryByTestId("eda-volcano-gene-PF3D7_0100400")).toBe(null);
    expect(screen.getByTestId("eda-volcano-selection")).toHaveTextContent(
      "2 genes selected",
    );
  });

  it("reads out every selected gene with its effect size and p-value", () => {
    useEdaStore.getState().applyViz(VOLCANO);
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    const rows = screen.getAllByTestId(/^eda-volcano-gene-/);
    expect(rows.map((row) => row.getAttribute("data-testid"))).toEqual([
      "eda-volcano-gene-PF3D7_0100200",
      "eda-volcano-gene-PF3D7_0100300",
    ]);
    expect(rows[0]).toHaveTextContent("PF3D7_0100200");
    expect(rows[0]).toHaveTextContent("3.94");
    expect(rows[0]).toHaveTextContent("1.38e-4");
    expect(rows[1]).toHaveTextContent("-2.50");
    expect(rows[1]).toHaveTextContent("4.00e-3");
  });

  it("caps the read-out list and says how many genes it holds back", () => {
    const points = Array.from({ length: 60 }, (_, index) => ({
      pointId: `PF3D7_${String(index).padStart(6, "0")}`,
      effectSize: 2 + index,
      pValue: 1e-6,
      adjustedPValue: 1e-6,
      retained: true,
    }));
    useEdaStore
      .getState()
      .applyViz({ ...VOLCANO, points, totalPoints: 60, retainedPoints: 60 });
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(screen.getAllByTestId(/^eda-volcano-gene-/)).toHaveLength(50);
    expect(screen.getByTestId("eda-volcano-readout-cap")).toHaveTextContent(
      "The first 50 of 60 selected genes are listed.",
    );
  });

  it("re-counts on a threshold change without asking the server for anything", async () => {
    useEdaStore.getState().applyViz(VOLCANO);
    let vizCalls = 0;
    server.use(
      http.post(`${BASE}/api/v1/eda/viz`, () => {
        vizCalls += 1;
        return HttpResponse.json(VOLCANO);
      }),
    );
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.clear(screen.getByLabelText("Effect size threshold"));
    await userEvent.type(screen.getByLabelText("Effect size threshold"), "3");
    await waitFor(() => {
      expect(screen.getByTestId("eda-volcano-selection")).toHaveTextContent(
        "1 gene selected",
      );
    });
    expect(vizCalls).toBe(0);
  });

  it("writes the threshold edit into the store so export and chat agree", async () => {
    useEdaStore.getState().applyViz(VOLCANO);
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.selectOptions(screen.getByLabelText("Direction"), "upOnly");
    await waitFor(() => {
      expect(useEdaStore.getState().volcanoThresholds.direction).toBe("upOnly");
    });
    expect(screen.getByTestId("eda-volcano-selection")).toHaveTextContent(
      "1 gene selected",
    );
  });

  it("keeps the significance threshold client side too", async () => {
    useEdaStore.getState().applyViz(VOLCANO);
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.clear(screen.getByLabelText("Significance threshold"));
    await userEvent.type(screen.getByLabelText("Significance threshold"), "0.001");
    await waitFor(() => {
      expect(useEdaStore.getState().volcanoThresholds.significanceThreshold).toBe(
        0.001,
      );
    });
    expect(screen.getByTestId("eda-volcano-selection")).toHaveTextContent(
      "1 gene selected",
    );
  });

  it("reports the point it could not plot", () => {
    useEdaStore.getState().applyViz(VOLCANO);
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(screen.getByTestId("eda-viz-volcano-dropped")).toHaveTextContent(
      "1 point without a p-value was not plotted",
    );
  });

  it("draws a scatter for chart scatter, with no threshold controls", () => {
    useEdaStore.getState().applyViz({ ...VOLCANO, chart: "scatter" });
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(screen.getByTestId("eda-viz-scatter")).toHaveAttribute("role", "img");
    expect(screen.queryByLabelText("Effect size threshold")).toBe(null);
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
      "bar plots are not available from this compute",
    );
  });

  it("says the same for a histogram and a boxplot", async () => {
    useEdaStore.getState().applyViz({ ...VOLCANO, chart: "histogram" });
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(screen.getByTestId("eda-viz-unsupported-chart")).toHaveTextContent(
      "histogram plots are not available from this compute",
    );
    useEdaStore.getState().applyViz({ ...VOLCANO, chart: "boxplot" });
    await waitFor(() => {
      expect(screen.getByTestId("eda-viz-unsupported-chart")).toHaveTextContent(
        "boxplot plots are not available from this compute",
      );
    });
  });

  it("reads the volcano for a completed compute, with no threshold in the body", async () => {
    let body: unknown = null;
    let url = "";
    server.use(
      http.post(`${BASE}/api/v1/eda/viz`, async ({ request }) => {
        body = await request.json();
        url = request.url;
        return HttpResponse.json(vizResponse(5));
      }),
    );
    useEdaStore.getState().applyJob(COMPLETED_JOB);
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId("eda-viz-volcano")).toHaveAttribute("role", "img");
    expect(body).toEqual({ datasetId: "DS_e973eadd57", chart: "volcano" });
    expect(url).toBe(`${BASE}/api/v1/eda/viz?siteId=plasmodb&conversationId=conv-1`);
    expect(screen.getByTestId("eda-volcano-selection")).toHaveTextContent(
      "2 genes selected",
    );
  });

  it("reads the volcano again when a second compute completes", async () => {
    const log = createRequestLog();
    let served = 0;
    server.use(
      http.post(`${BASE}/api/v1/eda/viz`, ({ requestId }) => {
        log.record(requestId);
        served += 1;
        return HttpResponse.json(vizResponse(served === 1 ? 5 : 77));
      }),
    );
    useEdaStore.getState().applyJob(COMPLETED_JOB);
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    await screen.findByTestId("eda-viz-volcano");
    expect(screen.getByTestId("eda-volcano-selection")).toHaveTextContent(
      "2 of 5 retained by the compute",
    );

    useEdaStore
      .getState()
      .applyJob({ ...COMPLETED_JOB, jobId: SECOND_JOB_ID, status: "complete" });
    await waitFor(() => {
      expect(screen.getByTestId("eda-volcano-selection")).toHaveTextContent(
        "2 of 77 retained by the compute",
      );
    });
    expect(log.count).toBe(2);
  });

  it("does not read the volcano again for a job that completes twice", async () => {
    const log = createRequestLog();
    server.use(
      http.post(`${BASE}/api/v1/eda/viz`, ({ requestId }) => {
        log.record(requestId);
        return HttpResponse.json(vizResponse(5));
      }),
    );
    useEdaStore.getState().applyJob(COMPLETED_JOB);
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    await screen.findByTestId("eda-viz-volcano");
    useEdaStore.getState().applyJob({ ...COMPLETED_JOB });
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(log.count).toBe(1);
  });

  it("shows a spinner while the volcano read is in flight", async () => {
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
    useEdaStore.getState().applyJob(COMPLETED_JOB);
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId("eda-viz-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("eda-viz-unavailable")).toBe(null);
    release();
    expect(await screen.findByTestId("eda-viz-volcano")).toHaveAttribute("role", "img");
    expect(screen.queryByTestId("eda-viz-loading")).toBe(null);
  });

  it("names a failed volcano read once, beside the plot and in no toast", async () => {
    server.use(
      http.post(`${BASE}/api/v1/eda/viz`, () =>
        HttpResponse.json(
          { detail: "Compute results are not available for the requested job." },
          { status: 400 },
        ),
      ),
    );
    useEdaStore.getState().applyJob(COMPLETED_JOB);
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

  it("asks for a VEuPathDB sign-in when the volcano read is refused for a missing login", async () => {
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
    useEdaStore.getState().applyJob(COMPLETED_JOB);
    render(<VizCell siteId="plasmodb" conversationId="conv-1" />, {
      wrapper: appQueryClientWrapper(),
    });
    expect(await screen.findByTestId("eda-viz-error")).toHaveTextContent(detail);
    expect(useAuthGateStore.getState().signInRequired).toBe(true);
    expect(useAuthGateStore.getState().signInReason).toBe(detail);
    expect(toastError.mock.calls).toEqual([[detail]]);
  });
});
