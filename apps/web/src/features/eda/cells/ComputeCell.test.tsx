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
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

const toastError = vi.fn();
vi.mock("sonner", () => ({ toast: { error: (m: string) => toastError(m) } }));

import { useEdaStore } from "@/state/eda";
import { appQueryClientWrapper } from "@/app/components/__fixtures__/appQueryClient";
import { ComputeCell } from "./ComputeCell";

const BASE = "http://localhost:3000";
const server = setupServer();
const JOB_ID = "db04204e5386396e1ca2cb78469ab6fb";

const SAMPLE_ENTITY = "ENT_8151325d";
const COUNTS_ENTITY = "ENT_fd574cd6";
const TEMPERATURE_VAR = "VAR_081ab087";

/** Every field the study route answers with; the schema drops no default now. */
function variable(overrides: Record<string, unknown>) {
  return {
    entityId: SAMPLE_ENTITY,
    variableId: TEMPERATURE_VAR,
    displayName: "temperature_condition",
    variableType: "string",
    filterType: "stringSet",
    dataShape: "categorical",
    isMultiValued: false,
    vocabulary: [],
    vocabularyTotal: 0,
    vocabularyNote: null,
    rangeMin: null,
    rangeMax: null,
    dateMin: null,
    dateMax: null,
    subFilterVariableIds: [],
    hideFrom: [],
    ...overrides,
  };
}

const GENE_ID_VARIABLE = variable({
  entityId: COUNTS_ENTITY,
  variableId: "VEUPATHDB_GENE_ID",
  displayName: "Gene ID",
});

const READ_COUNT_VARIABLE = variable({
  entityId: COUNTS_ENTITY,
  variableId: "SEQUENCE_READ_COUNT_SENSE",
  displayName: "Read count, sense",
  variableType: "integer",
  filterType: "numberRange",
  dataShape: "continuous",
  rangeMin: 0,
  rangeMax: 168342,
});

const TEMPERATURE_VARIABLE = variable({
  vocabulary: ["febrile", "normal"],
  vocabularyTotal: 2,
});

const TIMEPOINT_VAR = "VAR_timepoint";

const TIMEPOINT_VARIABLE = variable({
  variableId: TIMEPOINT_VAR,
  displayName: "timepoint",
  vocabulary: ["18h pbm", "24h pbm", "36h pbm"],
  vocabularyTotal: 3,
});

const STUDY_DETAIL = {
  datasetId: "DS_e973eadd57",
  studyId: "STUDY_e973eadd57",
  displayName: "Heat shock response",
  entities: [
    {
      entityId: SAMPLE_ENTITY,
      displayName: "Sample",
      displayNamePlural: "Samples",
      parentEntityId: null,
      variableCount: 1,
      hasGeneId: false,
    },
    {
      entityId: COUNTS_ENTITY,
      displayName: "pfal3D7 htseq counts",
      displayNamePlural: "pfal3D7 htseq counts",
      parentEntityId: SAMPLE_ENTITY,
      variableCount: 2,
      hasGeneId: true,
    },
  ],
  variables: [
    TEMPERATURE_VARIABLE,
    TIMEPOINT_VARIABLE,
    GENE_ID_VARIABLE,
    READ_COUNT_VARIABLE,
  ],
  geneEntityId: COUNTS_ENTITY,
  geneEntityProblem: null,
  canSubset: true,
  canExportRows: true,
};

const ANALYSIS = {
  siteId: "plasmodb",
  datasetId: "DS_e973eadd57",
  studyId: "STUDY_e973eadd57",
  analysisId: "a-1",
  revision: 0,
  studyDisplayName: "Heat shock response",
  displayName: "Unsaved analysis",
  numFilters: 0,
  numComputations: 0,
  filters: [],
  filterSummaries: [],
  entityCounts: [],
  canExportRows: true,
};

const EXPECTED_CONFIGURATION = {
  identifierVariable: {
    entityId: COUNTS_ENTITY,
    variableId: "VEUPATHDB_GENE_ID",
  },
  valueVariable: {
    entityId: COUNTS_ENTITY,
    variableId: "SEQUENCE_READ_COUNT_SENSE",
  },
  comparator: {
    variable: { entityId: SAMPLE_ENTITY, variableId: TEMPERATURE_VAR },
    groupA: [{ label: "normal" }],
    groupB: [{ label: "febrile" }],
  },
  differentialExpressionMethod: "DESeq",
  pValueFloor: "1e-200",
};

/** One entry per HTTP request. The interceptor may invoke a resolver more than
 * once for the same request, so entries are keyed by request id. */
function createRequestLog() {
  const byRequest = new Map<string, unknown>();
  return {
    record: async (requestId: string, request: Request) => {
      if (!byRequest.has(requestId)) byRequest.set(requestId, await request.json());
    },
    get bodies() {
      return [...byRequest.values()];
    },
  };
}

function jobResponse(status: string) {
  return {
    analysis: ANALYSIS,
    job: {
      jobId: JOB_ID,
      taskId: null,
      appName: "differentialexpression",
      status,
    },
    step: null,
  };
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
beforeEach(() => {
  toastError.mockClear();
  useEdaStore.getState().reset();
  useEdaStore.getState().applyAnalysisState(ANALYSIS);
  server.use(
    http.get(`${BASE}/api/v1/eda/studies/DS_e973eadd57`, () =>
      HttpResponse.json(STUDY_DETAIL),
    ),
  );
});

/** The analysis descriptor the conversation route answers, with one compute. */
function timepointDescriptor(groupA: string[], groupB: string[]) {
  return {
    subset: { descriptor: [] },
    computations: [
      {
        computationId: "C3WiXt0",
        descriptor: {
          type: "differentialexpression",
          configuration: {
            identifierVariable: {
              entityId: COUNTS_ENTITY,
              variableId: "VEUPATHDB_GENE_ID",
            },
            valueVariable: {
              entityId: COUNTS_ENTITY,
              variableId: "SEQUENCE_READ_COUNT_SENSE",
            },
            comparator: {
              variable: { entityId: SAMPLE_ENTITY, variableId: TIMEPOINT_VAR },
              groupA: groupA.map((label) => ({ label })),
              groupB: groupB.map((label) => ({ label })),
            },
            differentialExpressionMethod: "limma",
            pValueFloor: "1e-200",
          },
        },
        visualizations: [],
      },
    ],
  };
}

const PBM_DESCRIPTOR = timepointDescriptor(["24h pbm"], ["18h pbm", "36h pbm"]);

const REFERENCE = "Reference group (A)";
const COMPARISON = "Comparison group (B)";

function group(name: string) {
  return within(screen.getByRole("group", { name }));
}

async function fillConfig() {
  await userEvent.selectOptions(
    await screen.findByLabelText("Comparator variable"),
    TEMPERATURE_VAR,
  );
  await userEvent.click(group(REFERENCE).getByRole("checkbox", { name: "normal" }));
  await userEvent.click(group(COMPARISON).getByRole("checkbox", { name: "febrile" }));
}

describe("ComputeCell", () => {
  it("offers the study's computation and defaults to differential expression", async () => {
    render(<ComputeCell siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByLabelText("Analysis")).toHaveValue(
      "differentialexpression",
    );
  });

  it("offers DESeq2 as a label over the DESeq wire value", async () => {
    render(<ComputeCell siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByLabelText("Method")).toHaveValue("DESeq");
    expect(screen.getByRole("option", { name: "DESeq2" })).toHaveAttribute(
      "value",
      "DESeq",
    );
  });

  it("derives the value variable from the gene entity", async () => {
    render(<ComputeCell siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByLabelText("Value variable")).toHaveValue(
      "SEQUENCE_READ_COUNT_SENSE",
    );
  });

  it("names the missing gene id variable instead of offering a form", async () => {
    server.use(
      http.get(`${BASE}/api/v1/eda/studies/DS_e973eadd57`, () =>
        HttpResponse.json({ ...STUDY_DETAIL, variables: [TEMPERATURE_VARIABLE] }),
      ),
    );
    render(<ComputeCell siteId="plasmodb" conversationId="conv-1" />);
    expect(
      await screen.findByTestId("eda-compute-gene-entity-missing"),
    ).toHaveTextContent(
      "This study declares no VEUPATHDB_GENE_ID variable, so it cannot run differential expression.",
    );
    expect(screen.queryByLabelText("Comparator variable")).toBe(null);
  });

  it("keeps Run disabled until both groups are chosen", async () => {
    render(<ComputeCell siteId="plasmodb" conversationId="conv-1" />);
    const run = await screen.findByRole("button", { name: "Run compute" });
    expect(run).toBeDisabled();
    await fillConfig();
    expect(run).toBeEnabled();
  });

  it("sends the run-compute action with the recorded configuration", async () => {
    const log = createRequestLog();
    server.use(
      http.patch(
        `${BASE}/api/v1/conversations/conv-1/eda`,
        async ({ request, requestId }) => {
          await log.record(requestId, request);
          return HttpResponse.json(jobResponse("complete"));
        },
      ),
    );
    render(<ComputeCell siteId="plasmodb" conversationId="conv-1" />);
    await fillConfig();
    await userEvent.click(screen.getByRole("button", { name: "Run compute" }));

    await waitFor(() => {
      expect(log.bodies[0]).toEqual({
        action: "run-compute",
        computation: {
          type: "differentialexpression",
          configuration: EXPECTED_CONFIGURATION,
        },
      });
    });
  });

  it("mirrors the job into the store and shows its status", async () => {
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json(jobResponse("in-progress")),
      ),
    );
    render(<ComputeCell siteId="plasmodb" conversationId="conv-1" />);
    await fillConfig();
    await userEvent.click(screen.getByRole("button", { name: "Run compute" }));
    expect(await screen.findByTestId("eda-compute-progress")).toHaveTextContent(
      "in-progress",
    );
    await waitFor(() => {
      expect(useEdaStore.getState().jobs[JOB_ID]?.appName).toBe(
        "differentialexpression",
      );
    });
  });

  it(
    "polls by repeating the identical run-compute action",
    { timeout: 20_000 },
    async () => {
      const log = createRequestLog();
      server.use(
        http.patch(
          `${BASE}/api/v1/conversations/conv-1/eda`,
          async ({ request, requestId }) => {
            await log.record(requestId, request);
            return HttpResponse.json(
              jobResponse(log.bodies.length === 1 ? "queued" : "complete"),
            );
          },
        ),
      );
      render(<ComputeCell siteId="plasmodb" conversationId="conv-1" />);
      await fillConfig();
      await userEvent.click(screen.getByRole("button", { name: "Run compute" }));
      await waitFor(
        () => {
          expect(useEdaStore.getState().jobs[JOB_ID]?.status).toBe("complete");
        },
        { timeout: 10_000 },
      );
      expect(log.bodies).toHaveLength(2);
      expect(log.bodies[1]).toEqual(log.bodies[0]);
      expect(log.bodies[1]).toEqual({
        action: "run-compute",
        computation: {
          type: "differentialexpression",
          configuration: EXPECTED_CONFIGURATION,
        },
      });
    },
  );

  it("stops polling once the job is complete", { timeout: 20_000 }, async () => {
    const log = createRequestLog();
    server.use(
      http.patch(
        `${BASE}/api/v1/conversations/conv-1/eda`,
        async ({ request, requestId }) => {
          await log.record(requestId, request);
          return HttpResponse.json(jobResponse("complete"));
        },
      ),
    );
    render(<ComputeCell siteId="plasmodb" conversationId="conv-1" />);
    await fillConfig();
    await userEvent.click(screen.getByRole("button", { name: "Run compute" }));
    await waitFor(() => {
      expect(useEdaStore.getState().jobs[JOB_ID]?.status).toBe("complete");
    });
    expect(log.bodies).toHaveLength(1);
    await new Promise((resolve) => setTimeout(resolve, 3_000));
    expect(log.bodies).toHaveLength(1);
  });

  it("names a completed compute", async () => {
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json(jobResponse("complete")),
      ),
    );
    render(<ComputeCell siteId="plasmodb" conversationId="conv-1" />);
    await fillConfig();
    await userEvent.click(screen.getByRole("button", { name: "Run compute" }));
    expect(await screen.findByTestId("eda-compute-complete")).toHaveTextContent(
      "Compute complete.",
    );
  });

  it("names a status the service invented", async () => {
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json(jobResponse("scheduling")),
      ),
    );
    render(<ComputeCell siteId="plasmodb" conversationId="conv-1" />);
    await fillConfig();
    await userEvent.click(screen.getByRole("button", { name: "Run compute" }));
    expect(await screen.findByTestId("eda-compute-unknown-status")).toHaveTextContent(
      "The service answered with an unknown job status: scheduling.",
    );
    expect(screen.queryByTestId("eda-compute-progress")).toBe(null);
  });

  it("names a failed study read once, instead of an empty form", async () => {
    server.use(
      http.get(`${BASE}/api/v1/eda/studies/DS_e973eadd57`, () =>
        HttpResponse.json({ detail: "study read failed" }, { status: 500 }),
      ),
    );
    render(<ComputeCell siteId="plasmodb" conversationId="conv-1" />, {
      wrapper: appQueryClientWrapper(),
    });
    expect(await screen.findByTestId("eda-compute-study-error")).toHaveTextContent(
      "study read failed",
    );
    expect(screen.queryByLabelText("Comparator variable")).toBe(null);
    expect(screen.getAllByText("study read failed")).toHaveLength(1);
    expect(toastError).not.toHaveBeenCalled();
  });

  it("says a failed job cannot be re-run", async () => {
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json(jobResponse("failed")),
      ),
    );
    render(<ComputeCell siteId="plasmodb" conversationId="conv-1" />);
    await fillConfig();
    await userEvent.click(screen.getByRole("button", { name: "Run compute" }));
    expect(await screen.findByTestId("eda-compute-failed")).toHaveTextContent(
      "This compute failed and cannot be re-run. Change the configuration and run again.",
    );
    expect(screen.queryByRole("button", { name: "Re-run compute" })).toBe(null);
  });

  it("offers a re-run for an expired job", async () => {
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json(jobResponse("expired")),
      ),
    );
    render(<ComputeCell siteId="plasmodb" conversationId="conv-1" />);
    await fillConfig();
    await userEvent.click(screen.getByRole("button", { name: "Run compute" }));
    expect(await screen.findByTestId("eda-compute-expired")).toHaveTextContent(
      "This compute expired. Run it again to recompute the same result.",
    );
    expect(screen.getByRole("button", { name: "Re-run compute" })).toBeEnabled();
  });

  it("names a job the service does not know", async () => {
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json(jobResponse("no-such-job")),
      ),
    );
    render(<ComputeCell siteId="plasmodb" conversationId="conv-1" />);
    await fillConfig();
    await userEvent.click(screen.getByRole("button", { name: "Run compute" }));
    expect(await screen.findByTestId("eda-compute-missing")).toHaveTextContent(
      "The service has no job for this configuration.",
    );
  });

  it("reports a run that answered with no job", async () => {
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({ analysis: ANALYSIS, job: null, step: null }),
      ),
    );
    render(<ComputeCell siteId="plasmodb" conversationId="conv-1" />);
    await fillConfig();
    await userEvent.click(screen.getByRole("button", { name: "Run compute" }));
    expect(await screen.findByTestId("eda-compute-error")).toHaveTextContent(
      "The run answered with no compute job.",
    );
  });

  it("reports a failed run request once, beside the form", async () => {
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({ detail: "compute rejected" }, { status: 422 }),
      ),
    );
    render(<ComputeCell siteId="plasmodb" conversationId="conv-1" />, {
      wrapper: appQueryClientWrapper(),
    });
    await fillConfig();
    await userEvent.click(screen.getByRole("button", { name: "Run compute" }));
    expect(await screen.findByTestId("eda-compute-error")).toHaveTextContent(
      "compute rejected",
    );
    expect(screen.getAllByText("compute rejected")).toHaveLength(1);
    expect(toastError).not.toHaveBeenCalled();
  });

  it("disables in one group a label the other group holds", async () => {
    render(<ComputeCell siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.selectOptions(
      await screen.findByLabelText("Comparator variable"),
      TEMPERATURE_VAR,
    );
    await userEvent.click(group(REFERENCE).getByRole("checkbox", { name: "normal" }));
    expect(group(COMPARISON).getByRole("checkbox", { name: "normal" })).toBeDisabled();
    expect(group(COMPARISON).getByRole("checkbox", { name: "febrile" })).toBeEnabled();
  });

  it("starts with no groups when the analysis holds no compute", async () => {
    render(
      <ComputeCell
        siteId="plasmodb"
        conversationId="conv-1"
        descriptor={{ subset: { descriptor: [] }, computations: [] }}
      />,
    );
    expect(await screen.findByLabelText("Comparator variable")).toHaveValue("");
    expect(screen.queryAllByRole("checkbox")).toEqual([]);
    expect(screen.getByRole("button", { name: "Run compute" })).toBeDisabled();
  });

  it("shows the compute the analysis already holds, with Run disabled", async () => {
    render(
      <ComputeCell
        siteId="plasmodb"
        conversationId="conv-1"
        descriptor={PBM_DESCRIPTOR}
      />,
    );
    expect(await screen.findByLabelText("Comparator variable")).toHaveValue(
      TIMEPOINT_VAR,
    );
    expect(screen.getByLabelText("Method")).toHaveValue("limma");
    expect(screen.getByLabelText("Value variable")).toHaveValue(
      "SEQUENCE_READ_COUNT_SENSE",
    );
    expect(group(REFERENCE).getByRole("checkbox", { name: "24h pbm" })).toBeChecked();
    expect(
      group(REFERENCE).getByRole("checkbox", { name: "18h pbm" }),
    ).not.toBeChecked();
    expect(group(COMPARISON).getByRole("checkbox", { name: "18h pbm" })).toBeChecked();
    expect(group(COMPARISON).getByRole("checkbox", { name: "36h pbm" })).toBeChecked();
    expect(screen.getByRole("button", { name: "Run compute" })).toBeDisabled();
  });

  it("reseeds from a compute the analysis gains after the form opened", async () => {
    const { rerender } = render(
      <ComputeCell
        siteId="plasmodb"
        conversationId="conv-1"
        descriptor={PBM_DESCRIPTOR}
      />,
    );
    await screen.findByRole("checkbox", { name: "24h pbm", checked: true });
    rerender(
      <ComputeCell
        siteId="plasmodb"
        conversationId="conv-1"
        descriptor={timepointDescriptor(["36h pbm"], ["18h pbm", "24h pbm"])}
      />,
    );
    expect(group(REFERENCE).getByRole("checkbox", { name: "36h pbm" })).toBeChecked();
    expect(
      group(REFERENCE).getByRole("checkbox", { name: "24h pbm" }),
    ).not.toBeChecked();
    expect(group(COMPARISON).getByRole("checkbox", { name: "24h pbm" })).toBeChecked();
    expect(screen.getByRole("button", { name: "Run compute" })).toBeDisabled();
  });

  it("enables Run once the seeded compute changes", async () => {
    render(
      <ComputeCell
        siteId="plasmodb"
        conversationId="conv-1"
        descriptor={PBM_DESCRIPTOR}
      />,
    );
    await userEvent.click(
      await screen.findByRole("checkbox", { name: "36h pbm", checked: true }),
    );
    expect(screen.getByRole("button", { name: "Run compute" })).toBeEnabled();
  });

  it("disables Run when a group is emptied", async () => {
    render(
      <ComputeCell
        siteId="plasmodb"
        conversationId="conv-1"
        descriptor={PBM_DESCRIPTOR}
      />,
    );
    await userEvent.click(
      await screen.findByRole("checkbox", { name: "24h pbm", checked: true }),
    );
    await userEvent.click(group(REFERENCE).getByRole("checkbox", { name: "18h pbm" }));
    expect(screen.getByRole("button", { name: "Run compute" })).toBeDisabled();
  });

  it("writes several labels of one group in the vocabulary's order", async () => {
    const log = createRequestLog();
    server.use(
      http.patch(
        `${BASE}/api/v1/conversations/conv-1/eda`,
        async ({ request, requestId }) => {
          await log.record(requestId, request);
          return HttpResponse.json(jobResponse("complete"));
        },
      ),
    );
    render(<ComputeCell siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.selectOptions(
      await screen.findByLabelText("Comparator variable"),
      TIMEPOINT_VAR,
    );
    await userEvent.click(group(REFERENCE).getByRole("checkbox", { name: "24h pbm" }));
    await userEvent.click(group(COMPARISON).getByRole("checkbox", { name: "36h pbm" }));
    await userEvent.click(group(COMPARISON).getByRole("checkbox", { name: "18h pbm" }));
    await userEvent.click(screen.getByRole("button", { name: "Run compute" }));

    await waitFor(() => {
      expect(log.bodies[0]).toEqual({
        action: "run-compute",
        computation: {
          type: "differentialexpression",
          configuration: {
            ...EXPECTED_CONFIGURATION,
            comparator: {
              variable: { entityId: SAMPLE_ENTITY, variableId: TIMEPOINT_VAR },
              groupA: [{ label: "24h pbm" }],
              groupB: [{ label: "18h pbm" }, { label: "36h pbm" }],
            },
          },
        },
      });
    });
  });
});
