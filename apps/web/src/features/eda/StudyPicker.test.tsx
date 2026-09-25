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
import { StudyPicker } from "./StudyPicker";

const BASE = "http://localhost:3000";

const UPLOAD_URL = "https://plasmodb.org/plasmo/app/workspace/datasets";

function ownDataset(vdiId: string, state: string, message: string | null = null) {
  return {
    vdiId,
    name: `Upload ${vdiId}`,
    created: "2026-09-24T12:02:05Z",
    state,
    message,
    datasetId: state === "installed" ? `EDAUD_${vdiId}` : null,
    canSubset: state === "installed",
    canExportRows: state === "installed",
  };
}

const OWN_DATASETS = [
  ownDataset("4xZ5Q5pV1s4IM", "installed"),
  ownDataset("wtZ5dUpN8J0IE", "installing"),
  ownDataset(
    "MoZ5BBpM8U0IM",
    "failed",
    "Your counts file contains a non-count value ('-5' in sample 'S2', gene 'PF3D7_0500'). Every count must be a whole, non-negative number with no thousands separators.",
  ),
];

// Every picker reads the researcher's uploads on open.
const server = setupServer(
  http.get(`${BASE}/api/v1/eda/datasets`, () =>
    HttpResponse.json({ datasets: [], uploadUrl: UPLOAD_URL }),
  ),
);

const STUDY_ROW = {
  datasetId: "DS_e973eadd57",
  studyId: "STUDY_e973eadd57",
  displayName: "Heat shock response in sensitive mutants (LRR5, DHC)",
  shortDisplayName: "Heat shock",
  description: "RNA-Seq of heat shocked sensitive mutants.",
  sourceType: "curated",
  relevance: 0.91,
  canSubset: true,
  canExportRows: true,
  sites: ["plasmodb"],
  notHere: null,
};

const MOSQUITO_SENTENCE =
  "This study is on VectorBase; its genes are not PlasmoDB genes. Ask on VectorBase.";

const MOSQUITO_ROW = {
  ...STUDY_ROW,
  datasetId: "DS_89c1f6f48a",
  studyId: "STUDY_89c1f6f48a",
  displayName: "Antennal expression following a blood meal",
  shortDisplayName: "",
  sites: ["vectorbase"],
  notHere: MOSQUITO_SENTENCE,
};

const ANALYSIS = {
  siteId: "plasmodb",
  datasetId: "DS_e973eadd57",
  studyId: "STUDY_e973eadd57",
  analysisId: "a-1",
  revision: 0,
  studyDisplayName: STUDY_ROW.displayName,
  displayName: "Unsaved analysis",
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
    {
      entityId: "ENT_fd574cd6",
      entityDisplayName: "pfal3D7 htseq counts",
      count: 68640,
      unfilteredCount: 68640,
    },
  ],
  canExportRows: true,
};

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
beforeEach(() => {
  toastError.mockClear();
  useEdaStore.getState().reset();
});

describe("StudyPicker", () => {
  it("asks for two characters before it searches", () => {
    render(<StudyPicker siteId="plasmodb" conversationId="conv-1" />);
    expect(screen.getByTestId("eda-study-picker")).toHaveTextContent(
      "Type at least 2 characters to search studies.",
    );
  });

  it("lists a matching study with its short name and dataset id", async () => {
    server.use(
      http.get(`${BASE}/api/v1/eda/studies`, () =>
        HttpResponse.json({ studies: [STUDY_ROW] }),
      ),
    );
    render(<StudyPicker siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.type(screen.getByTestId("eda-study-search"), "heat shock");
    const row = await screen.findByTestId("eda-study-row-DS_e973eadd57");
    expect(row).toHaveTextContent("Heat shock response in sensitive mutants");
    expect(row).toHaveTextContent("Heat shock");
    expect(row).toHaveTextContent("DS_e973eadd57");
  });

  it("renders a row with no short name as the dataset id alone", async () => {
    server.use(
      http.get(`${BASE}/api/v1/eda/studies`, () =>
        HttpResponse.json({
          studies: [{ ...STUDY_ROW, shortDisplayName: "", sourceType: "" }],
        }),
      ),
    );
    render(<StudyPicker siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.type(screen.getByTestId("eda-study-search"), "heat shock");
    const row = await screen.findByTestId("eda-study-row-DS_e973eadd57");
    expect(row.textContent).not.toContain("undefined");
    expect(row).toHaveTextContent("DS_e973eadd57");
    expect(row).not.toHaveTextContent(
      "Heat shock response in sensitive mutants (LRR5, DHC)Heat shock",
    );
  });

  it("labels a study with the sites that publish it", async () => {
    server.use(
      http.get(`${BASE}/api/v1/eda/studies`, () =>
        HttpResponse.json({ studies: [STUDY_ROW] }),
      ),
    );
    render(<StudyPicker siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.type(screen.getByTestId("eda-study-search"), "heat shock");
    const label = await screen.findByTestId("eda-study-sites-DS_e973eadd57");
    expect(label).toHaveTextContent(/^plasmodb$/);
  });

  it("labels a study no genomics site publishes with the portal", async () => {
    server.use(
      http.get(`${BASE}/api/v1/eda/studies`, () =>
        HttpResponse.json({ studies: [{ ...STUDY_ROW, sites: ["portal"] }] }),
      ),
    );
    render(<StudyPicker siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.type(screen.getByTestId("eda-study-search"), "heat shock");
    const label = await screen.findByTestId("eda-study-sites-DS_e973eadd57");
    expect(label).toHaveTextContent(/^portal$/);
  });

  it("disables a study another site publishes and says where to ask", async () => {
    let patched = false;
    server.use(
      http.get(`${BASE}/api/v1/eda/studies`, () =>
        HttpResponse.json({ studies: [MOSQUITO_ROW, STUDY_ROW] }),
      ),
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, () => {
        patched = true;
        return HttpResponse.json({ analysis: ANALYSIS, step: null });
      }),
    );
    render(<StudyPicker siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.type(screen.getByTestId("eda-study-search"), "blood meal");
    const foreign = await screen.findByTestId("eda-study-row-DS_89c1f6f48a");
    expect(foreign).toBeDisabled();
    expect(foreign).toHaveAccessibleDescription(MOSQUITO_SENTENCE);
    expect(screen.getByTestId("eda-study-not-here-DS_89c1f6f48a")).toHaveTextContent(
      MOSQUITO_SENTENCE,
    );
    await userEvent.click(foreign);
    expect(patched).toBe(false);
    expect(screen.getByTestId("eda-study-row-DS_e973eadd57")).toBeEnabled();
    expect(screen.queryByTestId("eda-study-not-here-DS_e973eadd57")).toBe(null);
  });

  it("draws no site label when the sites are not known", async () => {
    server.use(
      http.get(`${BASE}/api/v1/eda/studies`, () =>
        HttpResponse.json({ studies: [{ ...STUDY_ROW, sites: [] }] }),
      ),
    );
    render(<StudyPicker siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.type(screen.getByTestId("eda-study-search"), "heat shock");
    await screen.findByTestId("eda-study-row-DS_e973eadd57");
    expect(screen.queryByTestId("eda-study-sites-DS_e973eadd57")).toBe(null);
  });

  it("says which site and query found nothing", async () => {
    server.use(
      http.get(`${BASE}/api/v1/eda/studies`, () => HttpResponse.json({ studies: [] })),
    );
    render(<StudyPicker siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.type(screen.getByTestId("eda-study-search"), "zzzz");
    expect(
      await screen.findByText("No study on PlasmoDB matches zzzz."),
    ).toBeInTheDocument();
  });

  it("sends the trimmed query and the site to the search route", async () => {
    let seenUrl = "";
    server.use(
      http.get(`${BASE}/api/v1/eda/studies`, ({ request }) => {
        seenUrl = request.url;
        return HttpResponse.json({ studies: [STUDY_ROW] });
      }),
    );
    render(<StudyPicker siteId="toxodb" conversationId="conv-1" />);
    await userEvent.type(screen.getByTestId("eda-study-search"), "heat shock");
    await screen.findByTestId("eda-study-row-DS_e973eadd57");
    expect(seenUrl).toContain("siteId=toxodb");
    expect(seenUrl).toContain("q=heat+shock");
  });

  it("binds the analysis on click and hydrates the store", async () => {
    let patchBody: unknown = null;
    server.use(
      http.get(`${BASE}/api/v1/eda/studies`, () =>
        HttpResponse.json({ studies: [STUDY_ROW] }),
      ),
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, async ({ request }) => {
        patchBody = await request.clone().json();
        return HttpResponse.json({ analysis: ANALYSIS, step: null });
      }),
    );
    render(<StudyPicker siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.type(screen.getByTestId("eda-study-search"), "heat shock");
    await userEvent.click(await screen.findByTestId("eda-study-row-DS_e973eadd57"));
    await waitFor(() => {
      expect(useEdaStore.getState().binding?.analysisId).toBe("a-1");
    });
    expect(patchBody).toEqual({
      action: "bind",
      siteId: "plasmodb",
      datasetId: "DS_e973eadd57",
    });
    expect(useEdaStore.getState().analysis?.entityCounts).toHaveLength(2);
    expect(useEdaStore.getState().analysis?.entityCounts[0]?.unfilteredCount).toBe(12);
  });

  it("reports a failed search once, instead of showing an empty list", async () => {
    server.use(
      http.get(`${BASE}/api/v1/eda/studies`, () =>
        HttpResponse.json({ detail: "upstream is down" }, { status: 502 }),
      ),
    );
    render(<StudyPicker siteId="plasmodb" conversationId="conv-1" />, {
      wrapper: appQueryClientWrapper(),
    });
    await userEvent.type(screen.getByTestId("eda-study-search"), "heat shock");
    expect(await screen.findByTestId("eda-study-search-error")).toHaveTextContent(
      "upstream is down",
    );
    expect(screen.queryByTestId("eda-study-results")).toBe(null);
    expect(screen.getAllByText("upstream is down")).toHaveLength(1);
    expect(toastError).not.toHaveBeenCalled();
  });

  it("lists the studies a Retry finds after the first search failed", async () => {
    let attempt = 0;
    server.use(
      http.get(`${BASE}/api/v1/eda/studies`, () => {
        attempt += 1;
        return attempt === 1
          ? HttpResponse.json({ detail: "upstream is down" }, { status: 502 })
          : HttpResponse.json({ studies: [STUDY_ROW] });
      }),
    );
    render(<StudyPicker siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.type(screen.getByTestId("eda-study-search"), "heat shock");
    const failure = await screen.findByTestId("eda-study-search-error");
    expect(failure).toHaveTextContent("upstream is down");

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    const row = await screen.findByTestId("eda-study-row-DS_e973eadd57");
    expect(row).toHaveTextContent("Heat shock response in sensitive mutants");
    expect(screen.queryByTestId("eda-study-search-error")).toBe(null);
  });

  it("keeps the binding untouched when the bind PATCH fails", async () => {
    server.use(
      http.get(`${BASE}/api/v1/eda/studies`, () =>
        HttpResponse.json({ studies: [STUDY_ROW] }),
      ),
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({ detail: "bind failed" }, { status: 500 }),
      ),
    );
    render(<StudyPicker siteId="plasmodb" conversationId="conv-1" />);
    await userEvent.type(screen.getByTestId("eda-study-search"), "heat shock");
    const row = await screen.findByTestId("eda-study-row-DS_e973eadd57");
    await userEvent.click(row);
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith("bind failed");
    });
    expect(useEdaStore.getState().binding).toBe(null);
    expect(row).toBeEnabled();
  });

  it("lists the researcher's own datasets before anything is typed", async () => {
    server.use(
      http.get(`${BASE}/api/v1/eda/datasets`, () =>
        HttpResponse.json({ datasets: OWN_DATASETS, uploadUrl: UPLOAD_URL }),
      ),
    );
    render(<StudyPicker siteId="plasmodb" conversationId="conv-1" />);

    const section = await screen.findByTestId("eda-your-datasets");
    expect(section).toHaveTextContent("Your datasets");
    expect(
      await screen.findByTestId("eda-own-dataset-4xZ5Q5pV1s4IM"),
    ).toHaveTextContent("Upload 4xZ5Q5pV1s4IM");
    expect(screen.getByRole("link", { name: "Upload on VEuPathDB" })).toHaveAttribute(
      "href",
      UPLOAD_URL,
    );
  });

  it("binds an installed upload by the study id VEuPathDB gave it", async () => {
    let patchBody: unknown = null;
    server.use(
      http.get(`${BASE}/api/v1/eda/datasets`, () =>
        HttpResponse.json({ datasets: OWN_DATASETS, uploadUrl: UPLOAD_URL }),
      ),
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, async ({ request }) => {
        patchBody = await request.clone().json();
        return HttpResponse.json({ analysis: ANALYSIS, step: null });
      }),
    );
    render(<StudyPicker siteId="plasmodb" conversationId="conv-1" />);

    const row = await screen.findByTestId("eda-own-dataset-4xZ5Q5pV1s4IM");
    await userEvent.click(
      within(row).getByRole("button", { name: /Upload 4xZ5Q5pV1s4IM/ }),
    );

    await waitFor(() => {
      expect(patchBody).toEqual({
        action: "bind",
        siteId: "plasmodb",
        datasetId: "EDAUD_4xZ5Q5pV1s4IM",
      });
    });
  });

  it("offers no way to open an upload that is installing or failed", async () => {
    server.use(
      http.get(`${BASE}/api/v1/eda/datasets`, () =>
        HttpResponse.json({ datasets: OWN_DATASETS, uploadUrl: UPLOAD_URL }),
      ),
    );
    render(<StudyPicker siteId="plasmodb" conversationId="conv-1" />);

    const row = await screen.findByTestId("eda-own-dataset-wtZ5dUpN8J0IE");
    expect(row).toHaveTextContent("Installing on VEuPathDB");
    expect(within(row).queryByRole("button", { name: /Upload wtZ5dUpN8J0IE/ })).toBe(
      null,
    );
    const failed = screen.getByTestId("eda-own-dataset-MoZ5BBpM8U0IM");
    expect(within(failed).queryByRole("button", { name: /Upload MoZ5BBpM8U0IM/ })).toBe(
      null,
    );
  });

  it("shows VEuPathDB's own reason on a failed upload", async () => {
    server.use(
      http.get(`${BASE}/api/v1/eda/datasets`, () =>
        HttpResponse.json({ datasets: OWN_DATASETS, uploadUrl: UPLOAD_URL }),
      ),
    );
    render(<StudyPicker siteId="plasmodb" conversationId="conv-1" />);

    expect(
      await screen.findByTestId("eda-own-dataset-MoZ5BBpM8U0IM"),
    ).toHaveTextContent(
      "Your counts file contains a non-count value ('-5' in sample 'S2', gene 'PF3D7_0500').",
    );
  });
});
