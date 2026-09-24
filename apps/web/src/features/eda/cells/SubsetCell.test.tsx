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
import { appQueryClientWrapper } from "@/app/components/__fixtures__/appQueryClient";
import { SubsetCell } from "./SubsetCell";

const BASE = "http://localhost:3000";
const server = setupServer();

const SAMPLE = "ENT_8151325d";
const COUNTS_ENTITY = "ENT_fd574cd6";
const TEMPERATURE = "VAR_081ab087";

const STUDY_DETAIL = {
  datasetId: "DS_e973eadd57",
  studyId: "STUDY_e973eadd57",
  displayName: "Heat shock response in sensitive mutants (LRR5, DHC)",
  entities: [
    {
      entityId: SAMPLE,
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
      parentEntityId: SAMPLE,
      variableCount: 1,
      hasGeneId: true,
    },
  ],
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
    {
      entityId: COUNTS_ENTITY,
      variableId: "SEQUENCE_READ_COUNT_SENSE",
      displayName: "Read count, sense",
      variableType: "integer",
      filterType: "numberRange",
      dataShape: "continuous",
      isMultiValued: false,
      vocabulary: [],
      vocabularyTotal: 0,
      vocabularyNote: null,
      rangeMin: 0,
      rangeMax: 68640,
      dateMin: null,
      dateMax: null,
      subFilterVariableIds: [],
      hideFrom: [],
    },
  ],
  geneEntityId: COUNTS_ENTITY,
  geneEntityProblem: null,
  canSubset: true,
  canExportRows: true,
};

const QC_FLAG = "VAR_qc_internal";

const HIDDEN_VARIABLE = {
  entityId: SAMPLE,
  variableId: QC_FLAG,
  displayName: "Internal QC flag",
  variableType: "string",
  filterType: "stringSet",
  dataShape: "categorical",
  isMultiValued: false,
  vocabulary: ["pass", "fail"],
  vocabularyTotal: 2,
  vocabularyNote: null,
  rangeMin: null,
  rangeMax: null,
  dateMin: null,
  dateMax: null,
  subFilterVariableIds: [],
  hideFrom: ["variableTree"],
};

const HIDDEN_FILTER = {
  entityId: SAMPLE,
  variableId: QC_FLAG,
  type: "stringSet",
  stringSet: ["pass"],
};

function withHiddenVariable() {
  server.use(
    http.get(`${BASE}/api/v1/eda/studies/DS_e973eadd57`, () =>
      HttpResponse.json({
        ...STUDY_DETAIL,
        variables: [...STUDY_DETAIL.variables, HIDDEN_VARIABLE],
      }),
    ),
  );
}

const COUNTS_UNFILTERED = [
  { entityId: SAMPLE, entityDisplayName: "Sample", count: 12, unfilteredCount: 12 },
  {
    entityId: COUNTS_ENTITY,
    entityDisplayName: "pfal3D7 htseq counts",
    count: 68640,
    unfilteredCount: 68640,
  },
];

const COUNTS_FEBRILE: Record<string, { count: number; unfilteredCount: number }> = {
  [SAMPLE]: { count: 6, unfilteredCount: 12 },
  [COUNTS_ENTITY]: { count: 34320, unfilteredCount: 68640 },
};

const FEBRILE_FILTER = {
  entityId: SAMPLE,
  variableId: TEMPERATURE,
  type: "stringSet",
  stringSet: ["febrile"],
};

const DISTRIBUTION = {
  variableId: TEMPERATURE,
  variableDisplayName: "temperature_condition",
  labels: ["febrile", "normal"],
  values: [6, 6],
  subsetSize: 12,
  numVarValues: 12,
  numMissingCases: 0,
  isMultiValued: false,
};

function analysis(overrides: Record<string, unknown> = {}) {
  return {
    siteId: "plasmodb",
    datasetId: "DS_e973eadd57",
    studyId: "STUDY_e973eadd57",
    analysisId: "a-1",
    revision: 0,
    studyDisplayName: STUDY_DETAIL.displayName,
    displayName: "Unsaved analysis",
    numFilters: 0,
    numComputations: 0,
    filters: [],
    filterSummaries: [],
    entityCounts: COUNTS_UNFILTERED,
    canExportRows: true,
    ...overrides,
  };
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
beforeEach(() => {
  toastError.mockClear();
  useEdaStore.getState().reset();
  useEdaStore.getState().applyAnalysisState(analysis());
  server.use(
    http.get(`${BASE}/api/v1/eda/studies/DS_e973eadd57`, () =>
      HttpResponse.json(STUDY_DETAIL),
    ),
    http.post(`${BASE}/api/v1/eda/distribution`, () => HttpResponse.json(DISTRIBUTION)),
  );
});

describe("SubsetCell", () => {
  it("shows the root entity count against its unfiltered total", async () => {
    render(<SubsetCell siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId(`eda-entity-${SAMPLE}`)).toHaveTextContent(
      "12 of 12",
    );
  });

  it("shows the analysis's own counts before any live count arrives", async () => {
    useEdaStore.getState().applyAnalysisState(
      analysis({
        revision: 1,
        numFilters: 1,
        filters: [FEBRILE_FILTER],
        filterSummaries: ["temperature_condition is febrile"],
        entityCounts: [
          { entityId: SAMPLE, entityDisplayName: "Sample", ...COUNTS_FEBRILE[SAMPLE] },
          {
            entityId: COUNTS_ENTITY,
            entityDisplayName: "pfal3D7 htseq counts",
            ...COUNTS_FEBRILE[COUNTS_ENTITY],
          },
        ],
      }),
    );
    render(<SubsetCell siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId(`eda-entity-${SAMPLE}`)).toHaveTextContent(
      "6 of 12",
    );
    expect(screen.getByTestId(`eda-entity-${COUNTS_ENTITY}`)).toHaveTextContent(
      "34,320 of 68,640",
    );
  });

  it("lists the child entity with its own counts", async () => {
    render(<SubsetCell siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId(`eda-entity-${COUNTS_ENTITY}`)).toHaveTextContent(
      "68,640 of 68,640",
    );
  });

  it("shows the vocabulary size as a hint on a categorical variable", async () => {
    render(<SubsetCell siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId(`eda-variable-${TEMPERATURE}`)).toHaveTextContent(
      "2 values",
    );
  });

  it("names the numeric range of a continuous variable", async () => {
    render(<SubsetCell siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.click(
      await screen.findByTestId(`eda-entity-toggle-${COUNTS_ENTITY}`),
    );
    expect(
      screen.getByTestId("eda-variable-SEQUENCE_READ_COUNT_SENSE"),
    ).toHaveTextContent("0 to 68640");
  });

  it("counts every entity and patches the analysis when a filter is added", async () => {
    // msw resolves a handler more than once per request, so the bodies are
    // keyed by entity rather than accumulated.
    const countBodies = new Map<string, unknown>();
    let patchBody: unknown = null;
    server.use(
      http.post(`${BASE}/api/v1/eda/count`, async ({ request }) => {
        const body = (await request.clone().json()) as { entityId: string };
        countBodies.set(body.entityId, body);
        const counted = COUNTS_FEBRILE[body.entityId];
        return HttpResponse.json({ entityId: body.entityId, ...counted });
      }),
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, async ({ request }) => {
        patchBody = await request.clone().json();
        return HttpResponse.json({
          analysis: analysis({
            revision: 1,
            numFilters: 1,
            filters: [FEBRILE_FILTER],
            filterSummaries: ["temperature_condition is febrile"],
            entityCounts: [
              {
                entityId: SAMPLE,
                entityDisplayName: "Sample",
                ...COUNTS_FEBRILE[SAMPLE],
              },
              {
                entityId: COUNTS_ENTITY,
                entityDisplayName: "pfal3D7 htseq counts",
                ...COUNTS_FEBRILE[COUNTS_ENTITY],
              },
            ],
          }),
          job: null,
          step: null,
        });
      }),
    );

    render(<SubsetCell siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.click(await screen.findByTestId(`eda-variable-${TEMPERATURE}`));
    await userEvent.click(await screen.findByRole("checkbox", { name: "febrile" }));
    await userEvent.click(screen.getByRole("button", { name: "Apply filter" }));

    await waitFor(() => {
      expect(useEdaStore.getState().analysis?.revision).toBe(1);
    });
    expect(patchBody).toEqual({ action: "set-filters", filters: [FEBRILE_FILTER] });
    expect([...countBodies.keys()]).toEqual([SAMPLE, COUNTS_ENTITY]);
    expect(countBodies.get(SAMPLE)).toEqual({
      datasetId: "DS_e973eadd57",
      entityId: SAMPLE,
      filters: [FEBRILE_FILTER],
    });
    expect(countBodies.get(COUNTS_ENTITY)).toEqual({
      datasetId: "DS_e973eadd57",
      entityId: COUNTS_ENTITY,
      filters: [FEBRILE_FILTER],
    });
    expect(await screen.findByTestId(`eda-entity-${SAMPLE}`)).toHaveTextContent(
      "6 of 12",
    );
    expect(screen.getByTestId(`eda-entity-${COUNTS_ENTITY}`)).toHaveTextContent(
      "34,320 of 68,640",
    );
  });

  it("renders a chip for the filter the server echoed back", async () => {
    useEdaStore.getState().applyAnalysisState(
      analysis({
        revision: 1,
        numFilters: 1,
        filters: [FEBRILE_FILTER],
        filterSummaries: ["temperature_condition is febrile"],
      }),
    );
    render(<SubsetCell siteId="plasmodb" conversationId="conv-1" />);
    const chip = await screen.findByTestId(`eda-filter-chip-${SAMPLE}-${TEMPERATURE}`);
    await waitFor(() => {
      expect(chip).toHaveTextContent("temperature_condition");
    });
    expect(chip).toHaveTextContent("febrile");
  });

  it("removes a chip by replacing the whole filter array", async () => {
    let patchBody: unknown = null;
    server.use(
      http.post(`${BASE}/api/v1/eda/count`, async ({ request }) => {
        const body = (await request.clone().json()) as { entityId: string };
        return HttpResponse.json({
          entityId: body.entityId,
          count: 12,
          unfilteredCount: 12,
        });
      }),
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, async ({ request }) => {
        patchBody = await request.clone().json();
        return HttpResponse.json({
          analysis: analysis({ revision: 2 }),
          job: null,
          step: null,
        });
      }),
    );
    useEdaStore
      .getState()
      .applyAnalysisState(
        analysis({ revision: 1, numFilters: 1, filters: [FEBRILE_FILTER] }),
      );
    render(<SubsetCell siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Remove filter on temperature_condition",
      }),
    );
    await waitFor(() => {
      expect(patchBody).toEqual({ action: "set-filters", filters: [] });
    });
  });

  it("reports a filter it cannot parse rather than hiding it", async () => {
    useEdaStore.getState().applyAnalysisState(
      analysis({
        revision: 1,
        numFilters: 2,
        filters: [FEBRILE_FILTER, { type: "somethingNew", entityId: "E" }],
      }),
    );
    render(<SubsetCell siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId("eda-subset-unparsed-filters")).toHaveTextContent(
      "1 filter on this analysis cannot be edited here",
    );
  });

  it("says once, beside the filters, that the count is unavailable and rolls the edit back", async () => {
    server.use(
      http.post(`${BASE}/api/v1/eda/count`, () =>
        HttpResponse.json({ detail: "count failed" }, { status: 500 }),
      ),
    );
    render(<SubsetCell siteId="plasmodb" conversationId="conv-1" />, {
      wrapper: appQueryClientWrapper(),
    });
    await userEvent.click(await screen.findByTestId(`eda-variable-${TEMPERATURE}`));
    await userEvent.click(await screen.findByRole("checkbox", { name: "febrile" }));
    await userEvent.click(screen.getByRole("button", { name: "Apply filter" }));
    expect(await screen.findByTestId("eda-subset-count-error")).toHaveTextContent(
      "count failed",
    );
    await waitFor(() => {
      expect(useEdaStore.getState().localFilters).toBe(null);
    });
    expect(screen.getAllByText("count failed")).toHaveLength(1);
    expect(toastError).not.toHaveBeenCalled();
  });

  it("draws a bar chart for a categorical variable and reports the value coverage", async () => {
    render(<SubsetCell siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.click(await screen.findByTestId(`eda-variable-${TEMPERATURE}`));
    expect(await screen.findByTestId("eda-subset-sparkline-bar")).toHaveAttribute(
      "role",
      "img",
    );
    expect(screen.queryByTestId("eda-subset-sparkline-histogram")).toBe(null);
    expect(screen.getByTestId("eda-subset-coverage")).toHaveTextContent(
      "12 of 12 records have a value",
    );
  });

  it("draws a histogram for a continuous variable", async () => {
    server.use(
      http.post(`${BASE}/api/v1/eda/distribution`, () =>
        HttpResponse.json({
          variableId: "SEQUENCE_READ_COUNT_SENSE",
          variableDisplayName: "Read count, sense",
          labels: ["0", "1000"],
          values: [40000, 28640],
          subsetSize: 68640,
          numVarValues: 68640,
          numMissingCases: 0,
          isMultiValued: false,
        }),
      ),
    );
    render(<SubsetCell siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.click(
      await screen.findByTestId(`eda-entity-toggle-${COUNTS_ENTITY}`),
    );
    await userEvent.click(screen.getByTestId("eda-variable-SEQUENCE_READ_COUNT_SENSE"));
    expect(await screen.findByTestId("eda-subset-sparkline-histogram")).toHaveAttribute(
      "role",
      "img",
    );
    expect(screen.queryByTestId("eda-subset-sparkline-bar")).toBe(null);
  });

  it("warns that a multi-valued variable outruns the subset size", async () => {
    server.use(
      http.post(`${BASE}/api/v1/eda/distribution`, () =>
        HttpResponse.json({
          variableId: TEMPERATURE,
          variableDisplayName: "Species",
          labels: ["P. berghei", "P. falciparum", "P. yoelii"],
          values: [4011, 4130, 268],
          subsetSize: 4279,
          numVarValues: 8409,
          numMissingCases: 0,
          isMultiValued: true,
        }),
      ),
    );
    render(<SubsetCell siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.click(await screen.findByTestId(`eda-variable-${TEMPERATURE}`));
    expect(await screen.findByTestId("eda-subset-multivalued")).toHaveTextContent(
      "one record can carry several values, so these counts do not add up to the subset size",
    );
    expect(screen.getByTestId("eda-subset-coverage")).toHaveTextContent(
      "8,409 of 4,279 records have a value",
    );
  });

  it("counts the records a variable leaves without a value", async () => {
    server.use(
      http.post(`${BASE}/api/v1/eda/distribution`, () =>
        HttpResponse.json({ ...DISTRIBUTION, numVarValues: 9, numMissingCases: 3 }),
      ),
    );
    render(<SubsetCell siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.click(await screen.findByTestId(`eda-variable-${TEMPERATURE}`));
    expect(await screen.findByTestId("eda-subset-coverage")).toHaveTextContent(
      "9 of 12 records have a value, 3 missing",
    );
    expect(screen.queryByTestId("eda-subset-multivalued")).toBe(null);
  });

  it("reports once a study whose entity tree cannot be read", async () => {
    server.use(
      http.get(`${BASE}/api/v1/eda/studies/DS_e973eadd57`, () =>
        HttpResponse.json({ detail: "study read failed" }, { status: 500 }),
      ),
    );
    render(<SubsetCell siteId="plasmodb" conversationId="conv-1" />, {
      wrapper: appQueryClientWrapper(),
    });
    expect(await screen.findByTestId("eda-subset-study-error")).toHaveTextContent(
      "study read failed",
    );
    expect(screen.queryByTestId(`eda-entity-${SAMPLE}`)).toBe(null);
    expect(screen.getAllByText("study read failed")).toHaveLength(1);
    expect(toastError).not.toHaveBeenCalled();
  });

  it("names the distribution as unavailable without a second toast", async () => {
    server.use(
      http.post(`${BASE}/api/v1/eda/distribution`, () =>
        HttpResponse.json({ detail: "distribution failed" }, { status: 500 }),
      ),
    );
    render(<SubsetCell siteId="plasmodb" conversationId="conv-1" />, {
      wrapper: appQueryClientWrapper(),
    });
    await userEvent.click(await screen.findByTestId(`eda-variable-${TEMPERATURE}`));
    expect(
      await screen.findByTestId("eda-subset-distribution-error"),
    ).toHaveTextContent("distribution unavailable");
    expect(toastError).not.toHaveBeenCalled();
  });

  it("carries the distribution's failure reason on the unavailable marker", async () => {
    server.use(
      http.post(`${BASE}/api/v1/eda/distribution`, () =>
        HttpResponse.json({ detail: "distribution failed" }, { status: 500 }),
      ),
    );
    render(<SubsetCell siteId="plasmodb" conversationId="conv-1" />, {
      wrapper: appQueryClientWrapper(),
    });
    await userEvent.click(await screen.findByTestId(`eda-variable-${TEMPERATURE}`));
    const marker = await screen.findByTestId("eda-subset-distribution-error");
    expect(marker).toHaveAttribute("title", "distribution failed");
    expect(marker).toHaveTextContent(/^distribution unavailable: distribution failed$/);
    expect(within(marker).getByText(": distribution failed")).toHaveClass("sr-only");
    expect(marker).toHaveAccessibleName("distribution failed");
  });

  it("leaves out a variable the study hides from the variable tree", async () => {
    withHiddenVariable();
    render(<SubsetCell siteId="plasmodb" conversationId="conv-1" />);
    expect(await screen.findByTestId(`eda-variable-${TEMPERATURE}`)).toHaveTextContent(
      "temperature_condition",
    );
    expect(screen.queryByTestId(`eda-variable-${QC_FLAG}`)).toBe(null);
  });

  it("keeps the chip of a filter already in force on a hidden variable", async () => {
    let patchBody: unknown = null;
    withHiddenVariable();
    server.use(
      http.post(`${BASE}/api/v1/eda/count`, async ({ request }) => {
        const body = (await request.clone().json()) as { entityId: string };
        return HttpResponse.json({
          entityId: body.entityId,
          count: 12,
          unfilteredCount: 12,
        });
      }),
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, async ({ request }) => {
        patchBody = await request.clone().json();
        return HttpResponse.json({
          analysis: analysis({ revision: 2 }),
          job: null,
          step: null,
        });
      }),
    );
    useEdaStore
      .getState()
      .applyAnalysisState(
        analysis({ revision: 1, numFilters: 1, filters: [HIDDEN_FILTER] }),
      );
    render(<SubsetCell siteId="plasmodb" conversationId="conv-1" />);
    const chip = await screen.findByTestId(`eda-filter-chip-${SAMPLE}-${QC_FLAG}`);
    await waitFor(() => {
      expect(chip).toHaveTextContent("Internal QC flag");
    });
    expect(chip).toHaveTextContent("pass");

    await userEvent.click(
      screen.getByRole("button", { name: "Remove filter on Internal QC flag" }),
    );
    await waitFor(() => {
      expect(patchBody).toEqual({ action: "set-filters", filters: [] });
    });
  });

  it("sends the effective filters with the distribution request", async () => {
    let distributionBody: unknown = null;
    server.use(
      http.post(`${BASE}/api/v1/eda/distribution`, async ({ request }) => {
        distributionBody = await request.clone().json();
        return HttpResponse.json(DISTRIBUTION);
      }),
    );
    useEdaStore
      .getState()
      .applyAnalysisState(
        analysis({ revision: 1, numFilters: 1, filters: [FEBRILE_FILTER] }),
      );
    render(<SubsetCell siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.click(await screen.findByTestId(`eda-variable-${TEMPERATURE}`));
    await screen.findByTestId("eda-subset-sparkline-bar");
    expect(distributionBody).toEqual({
      datasetId: "DS_e973eadd57",
      entityId: SAMPLE,
      variableId: TEMPERATURE,
      filters: [FEBRILE_FILTER],
    });
  });
});
