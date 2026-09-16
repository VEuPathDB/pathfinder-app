// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { queryOptions } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { GeneSet, ParamSpec } from "@pathfinder/shared";

import type { BatchStreamEvent } from "@/features/workbench/api/streaming";

import {
  GENE_LIST_SET,
  NO_ORGANISM_SPECS,
  SEARCH_WITHOUT_PARAMETERS_SET,
  ORGANISM_SPECS,
  SEARCH_BACKED_SET,
  SITE_ORGANISMS,
  failedExperiment,
  finishedExperiment,
} from "./__fixtures__/experimentPanels";

const env: { geneSet: GeneSet; specs: ParamSpec[]; positives: string[] } = {
  geneSet: SEARCH_BACKED_SET,
  specs: ORGANISM_SPECS,
  positives: ["PF3D7_0709000"],
};

vi.mock("@/state/useWorkbenchStore", () => ({
  useWorkbenchStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      activeSetId: "set-1",
      positiveControls: env.positives,
      negativeControls: ["PF3D7_0930300"],
      expandedPanels: new Set(["batch"]),
      togglePanel: vi.fn(),
    }),
}));
vi.mock("@/state/useSessionStore", () => ({
  useSessionStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ selectedSite: "plasmodb" }),
}));
vi.mock("@/features/workbench/hooks/useGeneSetsQuery", () => ({
  useGeneSetsQuery: () => ({ data: [env.geneSet] }),
}));
vi.mock("@/lib/api/sites", () => ({
  paramSpecsOptions: (siteId: string, recordType: string, searchName: string) =>
    queryOptions({
      queryKey: ["param-specs", siteId, recordType, searchName] as const,
      queryFn: () => Promise.resolve(env.specs),
      enabled: searchName !== "",
    }),
}));
vi.mock("@pathfinder/shared/generated/hooks/useGetOrganisms", () => ({
  getOrganismsQueryOptions: () =>
    queryOptions({
      queryKey: ["organisms", "plasmodb"] as const,
      queryFn: () => Promise.resolve({ organisms: SITE_ORGANISMS }),
    }),
}));

const createBatchExperimentStream = vi.fn();
vi.mock("@/features/workbench/api", async (importActual) => ({
  ...(await importActual<Record<string, unknown>>()),
  createBatchExperimentStream: (...args: unknown[]) =>
    createBatchExperimentStream(...args),
}));

import { BatchPanel } from "./BatchPanel";

beforeEach(() => {
  env.geneSet = SEARCH_BACKED_SET;
  env.specs = ORGANISM_SPECS;
  env.positives = ["PF3D7_0709000"];
  createBatchExperimentStream.mockReset();
});

async function pickOrganism(name: string): Promise<void> {
  await userEvent.click(await screen.findByText(/Filter by organism/i));
  await userEvent.click(screen.getByText(name));
}

describe("BatchPanel", () => {
  it("runs one experiment per chosen organism and reports each one", async () => {
    async function* stream(): AsyncGenerator<BatchStreamEvent> {
      yield { type: "experiment_progress", data: { phase: "scoring" } };
      yield {
        type: "batch_complete",
        batchId: "batch-1",
        experiments: [
          finishedExperiment({
            id: "exp-pf",
            name: "gametocyte secreted (Plasmodium falciparum 3D7)",
            organism: "Plasmodium falciparum 3D7",
            precision: 0.8,
            sensitivity: 0.8,
            f1Score: 0.8,
            mcc: 0.6,
            totalResults: 155,
          }),
          finishedExperiment({
            id: "exp-pb",
            name: "gametocyte secreted (Plasmodium berghei ANKA)",
            organism: "Plasmodium berghei ANKA",
            precision: 0.5,
            sensitivity: 0.4,
            f1Score: 0.44,
            mcc: 0.12,
            totalResults: 98,
          }),
        ],
      };
    }
    createBatchExperimentStream.mockReturnValue(stream());
    render(<BatchPanel />);

    await pickOrganism("Plasmodium falciparum 3D7");
    await pickOrganism("Plasmodium berghei ANKA");
    await userEvent.click(screen.getByText(/Run 2 experiments/i));

    await waitFor(() =>
      expect(screen.getByTestId("batch-results")).toBeInTheDocument(),
    );
    const rows = screen.getAllByTestId("experiment-row");
    expect(rows.map((row) => row.getAttribute("data-run"))).toEqual([
      "Plasmodium falciparum 3D7",
      "Plasmodium berghei ANKA",
    ]);
    expect(rows[0]?.textContent).toContain("155");
    expect(rows[1]?.textContent).toContain("0.12");

    const request = createBatchExperimentStream.mock.calls[0]?.[0] as {
      base: { controlsSearchName: string; searchName: string; geneSetId: string };
      organismParamName: string;
      targetOrganisms: { organism: string }[];
    };
    expect(request.organismParamName).toBe("organism");
    expect(request.targetOrganisms.map((t) => t.organism)).toEqual([
      "Plasmodium falciparum 3D7",
      "Plasmodium berghei ANKA",
    ]);
    expect(request.base.searchName).toBe("GenesByRNASeq");
    expect(request.base.controlsSearchName).toBe("GeneByLocusTag");
    expect(request.base.geneSetId).toBe("set-1");
  });

  it("draws a row for an organism that failed, with its own error", async () => {
    async function* stream(): AsyncGenerator<BatchStreamEvent> {
      yield {
        type: "batch_complete",
        batchId: "batch-1",
        experiments: [
          finishedExperiment({
            id: "exp-pf",
            name: "gametocyte secreted (Plasmodium falciparum 3D7)",
            organism: "Plasmodium falciparum 3D7",
            precision: 0.8,
            sensitivity: 0.8,
            f1Score: 0.8,
            mcc: 0.6,
            totalResults: 155,
          }),
          failedExperiment({
            id: "exp-pb",
            name: "gametocyte secreted (Plasmodium berghei ANKA)",
            organism: "Plasmodium berghei ANKA",
            error: "An internal error occurred",
          }),
          finishedExperiment({
            id: "exp-pv",
            name: "gametocyte secreted (Plasmodium vivax P01)",
            organism: "Plasmodium vivax P01",
            precision: 0.6,
            sensitivity: 0.5,
            f1Score: 0.55,
            mcc: 0.2,
            totalResults: 61,
          }),
        ],
      };
    }
    createBatchExperimentStream.mockReturnValue(stream());
    render(<BatchPanel />);

    await pickOrganism("Plasmodium falciparum 3D7");
    await pickOrganism("Plasmodium berghei ANKA");
    await pickOrganism("Plasmodium vivax P01");
    await userEvent.click(screen.getByText(/Run 3 experiments/i));

    await waitFor(() =>
      expect(screen.getByTestId("batch-results")).toBeInTheDocument(),
    );
    const rows = screen.getAllByTestId("experiment-row");
    expect(rows.map((row) => row.getAttribute("data-run"))).toEqual([
      "Plasmodium falciparum 3D7",
      "Plasmodium berghei ANKA",
      "Plasmodium vivax P01",
    ]);
    expect(rows[1]?.textContent).toContain("An internal error occurred");
    expect(rows[2]?.textContent).toContain("61");
  });

  it("shows the refusal the backend sends in its own words", async () => {
    async function* stream(): AsyncGenerator<BatchStreamEvent> {
      yield {
        type: "batch_error",
        error:
          "This batch cannot vary by organism: the base names no search, so it " +
          "has no organism parameter to set.",
      };
    }
    createBatchExperimentStream.mockReturnValue(stream());
    render(<BatchPanel />);

    await pickOrganism("Plasmodium vivax P01");
    await userEvent.click(screen.getByText(/Run 1 experiments/i));

    await waitFor(() =>
      expect(screen.getByTestId("batch-error")).toHaveTextContent(
        "This batch cannot vary by organism: the base names no search, so it has " +
          "no organism parameter to set.",
      ),
    );
  });

  it("refuses a set that records no search, and offers no run control", async () => {
    env.geneSet = GENE_LIST_SET;
    render(<BatchPanel />);

    expect(
      await screen.findByText(
        /holds a fixed gene list and records no search, so an organism changes nothing/i,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/experiments$/i)).toBeNull();
    expect(createBatchExperimentStream).not.toHaveBeenCalled();
  });

  it("does not tell a set that records a search that it records none", async () => {
    env.geneSet = SEARCH_WITHOUT_PARAMETERS_SET;
    render(<BatchPanel />);

    expect(
      await screen.findByText(
        /records the search GenesWithSignalPeptide but not the parameters it ran with/i,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/records no search/i)).toBeNull();
  });

  it("says when the search declares no organism parameter", async () => {
    env.specs = NO_ORGANISM_SPECS;
    render(<BatchPanel />);

    expect(
      await screen.findByText(/declares no organism parameter/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Filter by organism/i)).toBeNull();
  });

  it("holds the run until positive controls are picked", async () => {
    env.positives = [];
    render(<BatchPanel />);

    await pickOrganism("Plasmodium vivax P01");
    expect(
      screen.getByText(/Pick positive controls in the Evaluate panel/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Run 1 experiments/i).closest("button")).toBeDisabled();
  });

  it("renders nothing without an active gene set", () => {
    env.geneSet = { ...SEARCH_BACKED_SET, id: "another-set" };
    const { container } = render(<BatchPanel />);
    expect(container).toBeEmptyDOMElement();
  });
});
