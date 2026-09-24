/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import type { InvestigationLedger } from "@pathfinder/shared/generated/types/InvestigationLedger";

import {
  BuildSection,
  FrameSection,
  IntentSection,
  VerificationSection,
} from "./LedgerPanelSections";

describe("IntentSection", () => {
  it("renders the classification, goal, and differential sides", () => {
    render(
      <IntentSection
        intent={{
          classification: "new_strategy",
          inferredGoal: "Find kinase drug targets",
          isDifferential: true,
          differentialSides: ["expressed", "not expressed"],
        }}
      />,
    );
    expect(screen.getByText("new_strategy")).toBeInTheDocument();
    expect(screen.getByText("Find kinase drug targets")).toBeInTheDocument();
    expect(screen.getByText("expressed")).toBeInTheDocument();
  });

  it("shows 'Not classified yet' for null", () => {
    render(<IntentSection intent={null} />);
    expect(screen.getByText(/not classified yet/i)).toBeInTheDocument();
  });

  it("shows 'Not classified yet' for undefined (the exclude_none wire gap) - does not crash", () => {
    render(<IntentSection intent={undefined} />);
    expect(screen.getByText(/not classified yet/i)).toBeInTheDocument();
  });
});

const FRAME_WITH_SPEC: InvestigationLedger["frame"] = {
  present: true,
  diff: null,
  criteriaCount: 2,
  boundCount: 2,
  openSlotCount: 1,
  droppedCount: 1,
  readyToBuild: false,
  needsUser: true,
  contrasts: [
    {
      criterionId: "gametocyte_enrichment",
      comparator: "gametocyte",
      reference: "asexual",
      direction: "up-regulated",
      summary: "up-regulated in gametocyte vs asexual",
    },
  ],
  structureRender: "(GenesByText INTERSECT GenesByTaxon)",
  spec: {
    goal: "find gametocyte genes",
    interpretedGoal: "find gametocyte genes",
    recordType: "transcript",
    organismScope: "Plasmodium falciparum",
    title: "Gametocyte genes",
    criteria: [
      {
        id: "c1",
        text: "product mentions gametocyte",
        searchName: "GenesByText",
        role: "seed",
        resolvedParams: {
          text_expression: { type: "string", value: "gametocyte" },
          text_fields: { type: "string", value: "product" },
        },
        openParams: [],
        confidence: 0.9,
      },
      {
        id: "c2",
        text: "restrict to Pf",
        searchName: "GenesByTaxon",
        role: "filter",
        resolvedParams: {},
        openParams: [
          { criterionId: "c2", paramName: "organism", question: "Which organism?" },
        ],
        confidence: 0.5,
      },
    ],
    dropped: [{ text: "ortholog map", reason: "search unavailable" }],
    openSlots: [
      { criterionId: "c2", paramName: "organism", question: "Which organism?" },
    ],
  },
};

describe("FrameSection detail", () => {
  it("renders only counts in summary mode (no criteria detail)", () => {
    render(<FrameSection frame={FRAME_WITH_SPEC} />);
    expect(screen.queryByText("GenesByText")).not.toBeInTheDocument();
  });

  it("renders criteria, resolved params, structure and dropped in detail mode", () => {
    render(<FrameSection frame={FRAME_WITH_SPEC} detail />);
    expect(screen.getByText("GenesByText")).toBeInTheDocument();
    expect(screen.getByText(/product mentions gametocyte/)).toBeInTheDocument();
    expect(screen.getByText(/text_fields/)).toBeInTheDocument();
    expect(screen.getByText(/Which organism\?/)).toBeInTheDocument();
    expect(
      screen.getByText("(GenesByText INTERSECT GenesByTaxon)"),
    ).toBeInTheDocument();
    expect(screen.getByText(/search unavailable/)).toBeInTheDocument();
  });
});

const BUILD_WITH_NODES = {
  pushedCount: 2,
  failedCount: 1,
  skippedCount: 0,
  zeroResultSteps: [],
  needsRecovery: true,
  recoveryKind: "search_replan" as const,
  succeeded: false,
  wdkStrategyId: 42,
  wdkUrl: "https://plasmodb.org/s/42",
  nodeResults: [
    { nodeId: "n1", searchName: "GenesByText", count: 61, status: "ok" as const },
    {
      nodeId: "n2",
      searchName: "GenesByOrthologs",
      status: "failed" as const,
      error: "Answer Params must be null",
    },
  ],
};

describe("BuildSection detail", () => {
  it("renders per-node results and the strategy link in detail mode", () => {
    render(<BuildSection build={BUILD_WITH_NODES} detail />);
    expect(screen.getByText("GenesByText")).toBeInTheDocument();
    expect(screen.getByText(/61/)).toBeInTheDocument();
    expect(screen.getByText("GenesByOrthologs")).toBeInTheDocument();
    expect(screen.getByText(/Answer Params must be null/)).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      "https://plasmodb.org/s/42",
    );
  });

  it("omits node detail in summary mode", () => {
    render(<BuildSection build={BUILD_WITH_NODES} />);
    expect(screen.queryByText("GenesByOrthologs")).not.toBeInTheDocument();
  });

  it("labels combine nodes 'Combine', never the raw __combine__ sentinel", () => {
    const build = {
      ...BUILD_WITH_NODES,
      nodeResults: [
        { nodeId: "n1", searchName: "GenesByText", count: 61, status: "ok" as const },
        { nodeId: "n3", searchName: "__combine__", count: 42, status: "ok" as const },
      ],
    };
    render(<BuildSection build={build} detail />);
    expect(screen.getByText("Combine")).toBeInTheDocument();
    expect(screen.queryByText("__combine__")).not.toBeInTheDocument();
  });
});

const VERIFY_WITH_DIGEST = {
  complete: true,
  successful: true,
  digest: {
    disposition: "done" as const,
    prose: "The strategy returned 61 gametocyte genes.",
    reason: "sizes look right",
    success: true,
    keyFindings: ["61 genes overlap the gold set"],
    caveats: ["product-name search matched 0"],
  },
};

describe("sections tolerate the optional lists exclude_none drops", () => {
  it("renders an intent with no differential sides", () => {
    render(
      <IntentSection
        intent={{
          classification: "new_strategy",
          inferredGoal: "Find kinases",
        }}
      />,
    );
    expect(screen.getByText("Find kinases")).toBeInTheDocument();
  });

  it("renders a build with no zero-result steps and no counts", () => {
    render(
      <BuildSection
        build={{
          succeeded: false,
          nodeResults: [],
          wdkStrategyId: null,
          wdkUrl: null,
        }}
      />,
    );
    expect(screen.getByText("recovery kind")).toBeInTheDocument();
    expect(screen.getByText("none")).toBeInTheDocument();
  });

  it("renders a spec with no criteria and no dropped criteria", () => {
    render(
      <FrameSection
        frame={{ ...FRAME_WITH_SPEC, spec: { title: "Empty spec" } }}
        detail
      />,
    );
    expect(screen.queryByText("GenesByText")).not.toBeInTheDocument();
  });
});

describe("VerificationSection detail", () => {
  it("renders prose, findings and caveats in detail mode", () => {
    render(<VerificationSection verification={VERIFY_WITH_DIGEST} detail />);
    expect(screen.getByText(/61 gametocyte genes/)).toBeInTheDocument();
    expect(screen.getByText(/61 genes overlap the gold set/)).toBeInTheDocument();
    expect(screen.getByText(/product-name search matched 0/)).toBeInTheDocument();
  });

  it("names the study steps whose check is pending", () => {
    render(
      <VerificationSection
        verification={{
          ...VERIFY_WITH_DIGEST,
          digest: { ...VERIFY_WITH_DIGEST.digest, pendingChecks: ["step_de"] },
        }}
        detail
      />,
    );
    expect(screen.getByText("pending checks")).toBeInTheDocument();
    expect(screen.getByText("step_de")).toBeInTheDocument();
  });

  it("shows a pass with a pending check as pending, not as a pass", () => {
    render(
      <VerificationSection
        verification={{
          ...VERIFY_WITH_DIGEST,
          successful: false,
          digest: { ...VERIFY_WITH_DIGEST.digest, pendingChecks: ["step_de"] },
        }}
      />,
    );
    expect(screen.getByText("1 pending")).toBeInTheDocument();
    // The one "yes" left is the complete row's.
    expect(screen.getAllByText("yes")).toHaveLength(1);
    expect(screen.queryByText("no")).not.toBeInTheDocument();
  });

  it("omits digest prose in summary mode", () => {
    render(<VerificationSection verification={VERIFY_WITH_DIGEST} />);
    expect(screen.queryByText(/61 gametocyte genes/)).not.toBeInTheDocument();
  });
});
