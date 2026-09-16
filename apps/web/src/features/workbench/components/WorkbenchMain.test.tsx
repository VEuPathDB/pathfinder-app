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
  membershipDigest: "0000000000000011",
  createdAt: "2026-09-04T00:00:00Z",
};

const SEARCH_BACKED_SET: GeneSet = {
  ...GENE_SET,
  source: "strategy",
  searchName: "GenesByRNASeqTgonME49",
  parameters: {
    fold_change: { type: "string", value: "2" },
    organism: { type: "multi-pick-vocabulary", values: ["Toxoplasma gondii ME49"] },
  },
};

let geneSets: GeneSet[] = [GENE_SET];

vi.mock("@/features/workbench/hooks/useGeneSetsQuery", () => ({
  useGeneSetsQuery: () => ({ data: geneSets }),
}));

const chatViewProps: { conversationId: string }[] = [];
vi.mock("@/features/conversation/ChatView", () => ({
  ChatView: (props: { conversationId: string }) => {
    chatViewProps.push(props);
    return null;
  },
}));

import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { createTestWrapper } from "@/lib/query/testing";
import { useSessionStore } from "@/state/useSessionStore";
import { useWorkbenchStore } from "@/state/useWorkbenchStore";
import { WorkbenchMain } from "./WorkbenchMain";

const SITE = "plasmodb";

function drawMain(signedIn: boolean) {
  useSessionStore.setState({ selectedSite: SITE });
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(authStatusOptions(SITE).queryKey, {
    signedIn,
    name: "Researcher",
    email: "researcher@upenn.edu",
  });
  return render(
    <Wrapper>
      <WorkbenchMain />
    </Wrapper>,
  );
}

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
    createdAt: "2026-09-14T12:00:00Z",
    completedAt: "2026-09-15T12:00:00Z",
    geneSetMembership: { geneCount: 155, digest: GENE_SET.membershipDigest },
  };
}

describe("WorkbenchMain", () => {
  beforeEach(() => {
    chatViewProps.length = 0;
    geneSets = [GENE_SET];
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
    drawMain(true);
    expect(screen.getByText("Evaluate")).toBeInTheDocument();
    expect(screen.getByText("Gene Confidence")).toBeInTheDocument();
  });

  it("asks a signed-out reader to sign in instead of asking for a first gene set", () => {
    drawMain(false);

    expect(screen.getByText("Sign in to see your gene sets")).toBeInTheDocument();
    expect(screen.queryByText("Welcome to the Workbench")).not.toBeInTheDocument();
  });

  it("welcomes a signed-in reader who has no active gene set", () => {
    useWorkbenchStore.setState({ activeSetId: null });

    drawMain(true);

    expect(screen.getByText("Welcome to the Workbench")).toBeInTheDocument();
  });

  it("reads the search parameters of the active set as values", () => {
    geneSets = [SEARCH_BACKED_SET];

    drawMain(true);

    const header = screen.getByText(/GenesByRNASeqTgonME49/);
    expect(header).toHaveTextContent("fold_change: 2");
    expect(header).toHaveTextContent("organism: Toxoplasma gondii ME49");
    expect(header).not.toHaveTextContent("[object Object]");
  });

  it("dates the evaluation the active set still matches", () => {
    drawMain(true);

    expect(screen.getByText("Evaluated Sep 15, 2026")).toBeInTheDocument();
  });

  it("says the evaluation is out of date once the set has been re-taken", () => {
    geneSets = [{ ...GENE_SET, geneCount: 168, membershipDigest: "0000000000000099" }];

    drawMain(true);

    expect(
      screen.getByText("Evaluated Sep 15, 2026 (scored 155 genes, out of date)"),
    ).toBeInTheDocument();
  });

  it("never uses an experiment id as a conversation id", () => {
    drawMain(true);
    expect(chatViewProps.map((p) => p.conversationId)).not.toContain(EXPERIMENT_ID);
  });
});
