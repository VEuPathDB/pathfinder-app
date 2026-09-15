// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { Experiment } from "@pathfinder/shared";
import type { ExperimentStreamEvent } from "@/features/workbench/api/streaming";

// jsdom has no canvas 2d context, so the echarts instance is a double.
vi.mock("@/lib/components/charts/echartsRegistry", () => ({
  initChart: () => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    isDisposed: () => false,
  }),
}));

// Confusion matrix tp=8 fp=2 tn=8 fn=2 → sensitivity=precision=F1=bal-acc=0.8,
// MCC=(64-4)/sqrt(10*10*10*10)=0.6. Same hand-computed values the backend
// metrics test asserts; here we verify the panel DISPLAYS them.
const EXPERIMENT: Experiment = {
  id: "exp-eval-1",
  config: {
    siteId: "plasmodb",
    recordType: "transcript",
    searchName: "GenesByTaxon",
    parameters: {},
    positiveControls: ["PF3D7_0709000", "PF3D7_1133400"],
    negativeControls: ["PF3D7_0930300"],
    controlsSearchName: "GeneByLocusTag",
    controlsParamName: "ds_gene_ids",
    controlsValueFormat: "newline",
    enableCrossValidation: false,
    kFolds: 5,
    enrichmentTypes: [],
    name: "My Set (evaluation)",
    description: "",
    mode: "single",
  },
  status: "completed",
  metrics: {
    confusionMatrix: {
      truePositives: 8,
      falsePositives: 2,
      trueNegatives: 8,
      falseNegatives: 2,
    },
    sensitivity: 0.8,
    specificity: 0.8,
    precision: 0.8,
    f1Score: 0.8,
    mcc: 0.6,
    balancedAccuracy: 0.8,
    totalPositives: 10,
    totalNegatives: 10,
  },
  enrichmentResults: [],
  crossValidation: null,
  truePositiveGenes: [{ id: "PF3D7_0709000" }, { id: "PF3D7_1133400" }],
  falsePositiveGenes: [{ id: "PF3D7_0220800" }],
  trueNegativeGenes: [{ id: "PF3D7_0930300" }],
  falseNegativeGenes: [{ id: "PF3D7_1343700" }],
  notes: null,
  batchId: null,
  benchmarkId: null,
  controlSetLabel: null,
  isPrimaryBenchmark: false,
  error: null,
  totalTimeSeconds: 12.5,
  createdAt: "2026-06-12T00:00:00Z",
  completedAt: "2026-06-12T00:01:00Z",
  wdkStrategyId: null,
  wdkStepId: null,
  robustness: null,
} as unknown as Experiment;

const storeState: Record<string, unknown> = {
  activeSetId: "set-1",
  positiveControls: ["PF3D7_0709000", "PF3D7_1133400"],
  negativeControls: ["PF3D7_0930300"],
  setPositiveControls: vi.fn(),
  setNegativeControls: vi.fn(),
  setLastExperiment: vi.fn(),
  expandedPanels: new Set(["evaluate"]),
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
const activeGeneSet: {
  id: string;
  siteId: string;
  recordType: string;
  searchName: string | null;
  parameters: Record<string, never> | null;
  name: string;
  geneIds: string[];
} = {
  id: "set-1",
  siteId: "plasmodb",
  recordType: "transcript",
  searchName: "GenesByTaxon",
  parameters: {},
  name: "My Set",
  geneIds: ["PF3D7_0100100", "PF3D7_0200200"],
};

vi.mock("@/features/workbench/hooks/useGeneSetsQuery", () => ({
  useGeneSetsQuery: () => ({ data: [activeGeneSet] }),
}));
vi.mock("@tanstack/react-query", async (importActual) => ({
  ...(await importActual<Record<string, unknown>>()),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

const createExperimentStream = vi.fn();
vi.mock("@/features/workbench/api", () => ({
  createExperimentStream: (...args: unknown[]) => createExperimentStream(...args),
}));
vi.mock("../ControlSetQuickPick", () => ({
  ControlSetQuickPick: () => <div data-testid="control-quick-pick" />,
}));
vi.mock("../GeneChipInput", () => ({
  GeneChipInput: ({ label }: { label: string }) => <div>{label}</div>,
}));

import { EvaluatePanel } from "./EvaluatePanel";

async function* completeStream(): AsyncGenerator<ExperimentStreamEvent> {
  yield { type: "experiment_progress", data: { phase: "scoring" } };
  yield { type: "experiment_complete", experiment: EXPERIMENT };
  yield { type: "experiment_end" };
}

describe("EvaluatePanel", () => {
  it("renders the revived panel with its run control", () => {
    render(
      <TooltipProvider>
        <EvaluatePanel />
      </TooltipProvider>,
    );
    expect(screen.getByText("Evaluate")).toBeInTheDocument();
    expect(screen.getByText(/Run evaluation/i)).toBeInTheDocument();
  });

  it("runs an evaluation and displays the computed classification metrics", async () => {
    createExperimentStream.mockReturnValue(completeStream());
    render(
      <TooltipProvider>
        <EvaluatePanel />
      </TooltipProvider>,
    );

    await userEvent.click(screen.getByText(/Run evaluation/i));

    // The panel rendered the experiment the stream returned: MCC=0.6 (raw) and
    // the 0.8 classification metrics, computed from confusion matrix 8/2/2/8.
    const mccCard = await screen.findByText("MCC");
    expect(mccCard.closest("[data-metric]")).toHaveTextContent("0.600");
    const f1Card = screen.getByText("F1 Score").closest("[data-metric]");
    expect(f1Card).toHaveTextContent("80.0%");

    // Real items: 2 true-positive genes (the recovered controls); expanding
    // the list shows the actual gene id.
    const tpButton = screen.getByText("True Positives").closest("button");
    expect(tpButton).toHaveTextContent("2");
    await userEvent.click(tpButton as HTMLElement);
    expect(screen.getByText("PF3D7_0709000")).toBeInTheDocument();

    // The config sent to the backend carried the real controls.
    const sentConfig = createExperimentStream.mock.calls[0]?.[0] as {
      positiveControls: string[];
      searchName: string;
      geneSetId: string;
    };
    expect(sentConfig.positiveControls).toEqual(["PF3D7_0709000", "PF3D7_1133400"]);
    expect(sentConfig.searchName).toBe("GenesByTaxon");
    // The run belongs to the set it evaluated, so reopening that set finds it.
    expect(sentConfig.geneSetId).toBe("set-1");
  });

  it("sends a wire-valid fold count when cross-validation is off", async () => {
    createExperimentStream.mockReturnValue(completeStream());
    render(
      <TooltipProvider>
        <EvaluatePanel />
      </TooltipProvider>,
    );

    await userEvent.click(screen.getByText(/Run evaluation/i));

    // CreateExperimentRequest.kFolds is 2..10; enableCrossValidation is the
    // switch, so an "off" run still carries the panel's fold count.
    const sentConfig = createExperimentStream.mock.calls[0]?.[0] as {
      enableCrossValidation: boolean;
      kFolds: number;
      targetGeneIds: string[] | undefined;
    };
    expect(sentConfig.enableCrossValidation).toBe(false);
    expect(sentConfig.kFolds).toBe(5);
    expect(sentConfig.targetGeneIds).toBeUndefined();
  });

  it("evaluates a pasted set by its gene ids instead of an empty search", async () => {
    activeGeneSet.searchName = null;
    activeGeneSet.parameters = null;
    createExperimentStream.mockReturnValue(completeStream());
    render(
      <TooltipProvider>
        <EvaluatePanel />
      </TooltipProvider>,
    );

    await userEvent.click(screen.getByText(/Run evaluation/i));

    // A pasted set has no search to re-run; the wire's gene-set mode takes
    // targetGeneIds and the backend makes no WDK step for it.
    const sentConfig = createExperimentStream.mock.calls[0]?.[0] as {
      targetGeneIds: string[] | undefined;
    };
    expect(sentConfig.targetGeneIds).toEqual(["PF3D7_0100100", "PF3D7_0200200"]);
    activeGeneSet.searchName = "GenesByTaxon";
    activeGeneSet.parameters = {};
  });

  it("surfaces a streamed experiment error", async () => {
    async function* errStream(): AsyncGenerator<ExperimentStreamEvent> {
      yield { type: "experiment_error", error: "WDK rejected the search" };
      yield { type: "experiment_end" };
    }
    createExperimentStream.mockReturnValue(errStream());
    render(
      <TooltipProvider>
        <EvaluatePanel />
      </TooltipProvider>,
    );
    await userEvent.click(screen.getByText(/Run evaluation/i));
    await waitFor(() =>
      expect(screen.getByTestId("evaluate-error")).toHaveTextContent(
        "WDK rejected the search",
      ),
    );
  });
});
