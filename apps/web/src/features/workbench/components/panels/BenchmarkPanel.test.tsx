// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { queryOptions } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ControlSet, GeneSet } from "@pathfinder/shared";

import type { BenchmarkStreamEvent } from "@/features/workbench/api/streaming";

import {
  CONTROL_SETS,
  GENE_LIST_SET,
  SEARCH_BACKED_SET,
  failedExperiment,
  finishedExperiment,
} from "./__fixtures__/experimentPanels";

const env: { geneSet: GeneSet; controlSets: ControlSet[] } = {
  geneSet: SEARCH_BACKED_SET,
  controlSets: CONTROL_SETS,
};

vi.mock("@/state/useWorkbenchStore", () => ({
  useWorkbenchStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      activeSetId: "set-1",
      positiveControls: ["PF3D7_0709000"],
      negativeControls: [],
      expandedPanels: new Set(["benchmark"]),
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
vi.mock("../../api/controlSets", () => ({
  controlSetsOptions: (siteId: string) =>
    queryOptions({
      queryKey: ["control-sets", siteId] as const,
      queryFn: () => Promise.resolve(env.controlSets),
    }),
}));

const createBenchmarkStream = vi.fn();
vi.mock("@/features/workbench/api", async (importActual) => ({
  ...(await importActual<Record<string, unknown>>()),
  createBenchmarkStream: (...args: unknown[]) => createBenchmarkStream(...args),
}));

import { BenchmarkPanel } from "./BenchmarkPanel";

beforeEach(() => {
  env.geneSet = SEARCH_BACKED_SET;
  env.controlSets = CONTROL_SETS;
  createBenchmarkStream.mockReset();
});

describe("BenchmarkPanel", () => {
  it("scores the set once per chosen control set", async () => {
    async function* stream(): AsyncGenerator<BenchmarkStreamEvent> {
      yield { type: "experiment_progress", data: { phase: "scoring" } };
      yield {
        type: "benchmark_complete",
        benchmarkId: "bench-1",
        experiments: [
          finishedExperiment({
            id: "exp-gam",
            name: "gametocyte secreted [gametocyte surface]",
            controlSetLabel: "gametocyte surface",
            precision: 0.8,
            sensitivity: 0.8,
            f1Score: 0.8,
            mcc: 0.6,
            totalResults: 155,
          }),
          finishedExperiment({
            id: "exp-mero",
            name: "gametocyte secreted [merozoite invasion]",
            controlSetLabel: "merozoite invasion",
            precision: 0.25,
            sensitivity: 0.2,
            f1Score: 0.22,
            mcc: -0.1,
            totalResults: 155,
          }),
        ],
      };
    }
    createBenchmarkStream.mockReturnValue(stream());
    render(<BenchmarkPanel />);

    await userEvent.click(await screen.findByText(/gametocyte surface/i));
    await userEvent.click(screen.getByText(/merozoite invasion/i));
    await userEvent.click(screen.getByText(/Run 2 control sets/i));

    await waitFor(() =>
      expect(screen.getByTestId("benchmark-results")).toBeInTheDocument(),
    );
    const rows = screen.getAllByTestId("experiment-row");
    expect(rows.map((row) => row.getAttribute("data-run"))).toEqual([
      "gametocyte surface",
      "merozoite invasion",
    ]);
    expect(rows[1]?.textContent).toContain("-0.10");

    const request = createBenchmarkStream.mock.calls[0]?.[0] as {
      base: { controlsParamName: string; geneSetId: string };
      controlSets: {
        label: string;
        positiveControls: string[];
        controlSetId: string;
        isPrimary: boolean;
      }[];
    };
    expect(request.base.controlsParamName).toBe("ds_gene_ids");
    expect(request.base.geneSetId).toBe("set-1");
    expect(request.controlSets.map((cs) => cs.label)).toEqual([
      "gametocyte surface",
      "merozoite invasion",
    ]);
    expect(request.controlSets.map((cs) => cs.isPrimary)).toEqual([true, false]);
    expect(request.controlSets[0]?.controlSetId).toBe("cs-gam");
    expect(request.controlSets[0]?.positiveControls).toEqual(["PF3D7_0304600"]);
  });

  it("draws a row for a control set whose run failed, with its own error", async () => {
    async function* stream(): AsyncGenerator<BenchmarkStreamEvent> {
      yield {
        type: "benchmark_complete",
        benchmarkId: "bench-1",
        experiments: [
          finishedExperiment({
            id: "exp-gam",
            name: "gametocyte secreted [gametocyte surface]",
            controlSetLabel: "gametocyte surface",
            precision: 0.8,
            sensitivity: 0.8,
            f1Score: 0.8,
            mcc: 0.6,
            totalResults: 155,
          }),
          failedExperiment({
            id: "exp-mero",
            name: "gametocyte secreted [merozoite invasion]",
            controlSetLabel: "merozoite invasion",
            error: "An internal error occurred",
          }),
        ],
      };
    }
    createBenchmarkStream.mockReturnValue(stream());
    render(<BenchmarkPanel />);

    await userEvent.click(await screen.findByText(/gametocyte surface/i));
    await userEvent.click(screen.getByText(/merozoite invasion/i));
    await userEvent.click(screen.getByText(/Run 2 control sets/i));

    await waitFor(() =>
      expect(screen.getByTestId("benchmark-results")).toBeInTheDocument(),
    );
    const rows = screen.getAllByTestId("experiment-row");
    expect(rows.map((row) => row.getAttribute("data-run"))).toEqual([
      "gametocyte surface",
      "merozoite invasion",
    ]);
    expect(rows[1]?.textContent).toContain("An internal error occurred");
  });

  it("cannot be run before a control set is chosen", async () => {
    render(<BenchmarkPanel />);

    expect(
      await screen.findByText(/Choose at least one control set/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Run 0 control sets/i).closest("button")).toBeDisabled();
    expect(createBenchmarkStream).not.toHaveBeenCalled();
  });

  it("benchmarks a set that holds only genes, because the controls vary, not the search", async () => {
    env.geneSet = GENE_LIST_SET;
    createBenchmarkStream.mockReturnValue(
      (async function* (): AsyncGenerator<BenchmarkStreamEvent> {})(),
    );
    render(<BenchmarkPanel />);

    await userEvent.click(await screen.findByText(/gametocyte surface/i));
    await userEvent.click(screen.getByText(/Run 1 control sets/i));

    await waitFor(() => expect(createBenchmarkStream).toHaveBeenCalled());
    const request = createBenchmarkStream.mock.calls[0]?.[0] as {
      base: { targetGeneIds: string[] | null; searchName: string };
    };
    expect(request.base.targetGeneIds).toEqual(["PF3D7_0100100", "PF3D7_0200200"]);
    expect(request.base.searchName).toBe("");
  });

  it("says where control sets come from when the site has none", async () => {
    env.controlSets = [];
    render(<BenchmarkPanel />);

    expect(
      await screen.findByText(/Save one from the Evaluate panel first/i),
    ).toBeInTheDocument();
  });

  it("renders nothing without an active gene set", () => {
    env.geneSet = { ...SEARCH_BACKED_SET, id: "another-set" };
    const { container } = render(<BenchmarkPanel />);
    expect(container).toBeEmptyDOMElement();
  });
});
