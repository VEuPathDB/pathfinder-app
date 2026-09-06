// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { Experiment, GeneSet } from "@pathfinder/shared";

const EXPERIMENT_ID = "exp_27ea249a782e";

const GENE_SET: GeneSet = {
  id: "set-1",
  name: "V3 Eval",
  siteId: "plasmodb",
  recordType: "gene",
  source: "paste",
  geneIds: ["PF3D7_0102900"],
  geneCount: 1,
  createdAt: "2026-09-04T00:00:00Z",
};

vi.mock("@/features/workbench/hooks/useGeneSetsQuery", () => ({
  useGeneSetsQuery: () => ({ data: [GENE_SET] }),
}));

const chatViewProps: { conversationId: string }[] = [];
vi.mock("@/features/conversation/ChatView", () => ({
  ChatView: (props: { conversationId: string }) => {
    chatViewProps.push(props);
    return null;
  },
}));

import { useWorkbenchStore } from "@/state/useWorkbenchStore";
import { WorkbenchMain } from "./WorkbenchMain";

function makeExperiment(): Experiment {
  return {
    id: EXPERIMENT_ID,
    config: {
      siteId: "plasmodb",
      recordType: "gene",
      searchName: "GeneByLocusTag",
      parameters: {},
      positiveControls: ["PF3D7_0102900"],
      negativeControls: [],
      controlsSearchName: "GeneByLocusTag",
      controlsParamName: "ds_gene_ids",
      controlsValueFormat: "newline",
      enableCrossValidation: false,
      kFolds: 5,
      enrichmentTypes: [],
      name: "V3 Eval (evaluation)",
      description: "",
      mode: "single",
    },
    status: "completed",
    truePositiveGenes: [{ id: "PF3D7_0102900" }],
  };
}

describe("WorkbenchMain", () => {
  beforeEach(() => {
    chatViewProps.length = 0;
    useWorkbenchStore.setState({
      activeSetId: "set-1",
      lastExperiment: makeExperiment(),
      lastExperimentSetId: "set-1",
      expandedPanels: new Set(),
    });
  });

  afterEach(() => {
    cleanup();
    useWorkbenchStore.getState().reset();
  });

  it("renders the panels for the active gene set", () => {
    render(<WorkbenchMain />);
    expect(screen.getByText("Evaluate")).toBeInTheDocument();
    expect(screen.getByText("Gene Confidence")).toBeInTheDocument();
  });

  it("never uses an experiment id as a conversation id", () => {
    render(<WorkbenchMain />);
    expect(chatViewProps.map((p) => p.conversationId)).not.toContain(EXPERIMENT_ID);
  });
});
