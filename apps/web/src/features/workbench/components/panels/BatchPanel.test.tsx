// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Experiment } from "@pathfinder/shared";
import type { BatchStreamEvent } from "@/features/workbench/api/streaming";

const storeState: Record<string, unknown> = {
  activeSetId: "set-1",
  positiveControls: ["PF3D7_0709000"],
  negativeControls: ["PF3D7_0930300"],
  expandedPanels: new Set(["batch"]),
  togglePanel: vi.fn(),
};

vi.mock("@/state/useWorkbenchStore", () => ({
  useWorkbenchStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector(storeState),
}));
vi.mock("@/state/useSessionStore", () => ({
  useSessionStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ selectedSite: "plasmodb" }),
}));
vi.mock("@/features/workbench/hooks/useGeneSetsQuery", () => ({
  useGeneSetsQuery: () => ({
    data: [
      {
        id: "set-1",
        siteId: "plasmodb",
        recordType: "transcript",
        searchName: "GenesByTaxon",
        parameters: {},
        name: "Kinases",
        geneIds: ["PF3D7_0100100"],
      },
    ],
  }),
}));

const createBatchExperimentStream = vi.fn();
vi.mock("@/features/workbench/api", () => ({
  createBatchExperimentStream: (...args: unknown[]) =>
    createBatchExperimentStream(...args),
}));

import { BatchPanel } from "./BatchPanel";

function exp(id: string, organism: string, mcc: number): Experiment {
  return {
    id,
    config: { name: organism },
    status: "completed",
    metrics: { mcc },
  } as unknown as Experiment;
}

describe("BatchPanel", () => {
  it("runs one experiment per organism and reports the completed batch", async () => {
    async function* stream(): AsyncGenerator<BatchStreamEvent> {
      yield { type: "experiment_progress", data: { phase: "scoring" } };
      yield {
        type: "batch_complete",
        batchId: "batch-1",
        experiments: [
          exp("exp-pf", "Plasmodium falciparum", 0.6),
          exp("exp-pb", "Plasmodium berghei", 0.42),
        ],
      };
    }
    createBatchExperimentStream.mockReturnValue(stream());
    render(<BatchPanel />);

    await userEvent.type(
      screen.getByPlaceholderText(/Plasmodium falciparum/i),
      "Plasmodium falciparum\nPlasmodium berghei",
    );
    // The run button reflects the parsed organism count.
    const runBtn = screen.getByText(/Run 2 experiments/i);
    expect(runBtn.closest("button")).toBeEnabled();
    await userEvent.click(runBtn);

    await waitFor(() =>
      expect(screen.getByText(/2 experiments complete/i)).toBeInTheDocument(),
    );

    // The batch request carried both organisms + the real controls/base config.
    const call = createBatchExperimentStream.mock.calls[0] as [
      { positiveControls: string[]; searchName: string },
      string,
      { organism: string }[],
    ];
    expect(call[1]).toBe("organism");
    expect(call[2].map((t) => t.organism)).toEqual([
      "Plasmodium falciparum",
      "Plasmodium berghei",
    ]);
    expect(call[0].positiveControls).toEqual(["PF3D7_0709000"]);
    expect(call[0].searchName).toBe("GenesByTaxon");
  });

  it("renders nothing without an active gene set", () => {
    storeState["activeSetId"] = "missing";
    const { container } = render(<BatchPanel />);
    expect(container).toBeEmptyDOMElement();
    storeState["activeSetId"] = "set-1";
  });
});
