// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import type { Strategy } from "@pathfinder/shared";
import { computeStepCounts } from "@pathfinder/shared/generated/hooks/useComputeStepCounts";
import { createTestWrapper } from "@/lib/query/testing";
import { APPLY_OPERATION_MUTATION_KEY } from "@/features/strategy/mutations/useApplyOperation";
import { StrategyGraph } from "./StrategyGraph";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () => "/veupathdb/conversation/strategy-1/strategy",
  useParams: () => ({ siteId: "veupathdb", conversationId: "strategy-1" }),
}));

vi.mock("@xyflow/react", async () => {
  const React = await import("react");
  const flowContext = React.createContext(false);

  function useFlowProviderGuard() {
    if (!React.useContext(flowContext)) {
      throw new Error("[React Flow]: provider missing");
    }
  }

  return {
    ReactFlowProvider: ({ children }: { children: React.ReactNode }) =>
      React.createElement(flowContext.Provider, { value: true }, children),
    ReactFlow: ({ children }: { children?: React.ReactNode }) => {
      useFlowProviderGuard();
      return React.createElement("div", { "data-testid": "react-flow" }, children);
    },
    Background: () => React.createElement("div", { "data-testid": "flow-background" }),
    Controls: () => React.createElement("div", { "data-testid": "flow-controls" }),
    MiniMap: () => React.createElement("div", { "data-testid": "flow-minimap" }),
    Panel: ({ children }: { children?: React.ReactNode }) =>
      React.createElement("div", null, children),
    Handle: () => React.createElement("span", { "data-testid": "flow-handle" }),
    NodeToolbar: ({ children }: { children?: React.ReactNode }) =>
      React.createElement("div", null, children),
    useReactFlow: () => {
      useFlowProviderGuard();
      return { fitView: vi.fn() };
    },
    useNodesState: <T,>(initial: T[]) => {
      const [nodes, setNodes] = React.useState<T[]>(initial);
      return [nodes, setNodes, vi.fn()] as const;
    },
    useEdgesState: <T,>(initial: T[]) => {
      const [edges, setEdges] = React.useState<T[]>(initial);
      return [edges, setEdges, vi.fn()] as const;
    },
    ConnectionMode: { Loose: "loose" },
    MarkerType: { ArrowClosed: "arrowclosed" },
    Position: {
      Top: "top",
      Right: "right",
      Bottom: "bottom",
      Left: "left",
    },
    SelectionMode: { Partial: "partial" },
    useStore: () => "0|0|1",
  };
});

vi.mock("@/lib/api/sites", () => ({
  sitesOptions: () => ({
    queryKey: ["sites"],
    queryFn: async () => [],
  }),
}));

vi.mock("@pathfinder/shared/generated/hooks/useComputeStepCounts", () => ({
  computeStepCounts: vi.fn(async () => ({ counts: {} })),
}));

vi.mock("@pathfinder/shared/generated/hooks/usePushStrategy", () => ({
  pushStrategy: vi.fn(),
}));

const STRATEGY: Strategy = {
  id: "strategy-1",
  name: "Editable strategy",
  siteId: "plasmodb",
  recordType: "gene",
  steps: [
    {
      id: "step_1",
      kind: "search",
      displayName: "Genes by taxon",
      searchName: "GenesByTaxon",
      recordType: "gene",
      parameters: {
        organism: {
          type: "single-pick-vocabulary",
          value: "Plasmodium falciparum 3D7",
        },
      },
      isFiltered: false,
    },
  ],
  rootStepId: "step_1",
  isSaved: false,
  createdAt: "2026-01-01T00:00:00.000Z",
  updatedAt: "2026-01-01T00:00:00.000Z",
};

describe("StrategyGraph React Flow provider boundary", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders graph hooks under ReactFlowProvider", () => {
    const { Wrapper } = createTestWrapper();

    render(
      <Wrapper>
        <StrategyGraph
          strategy={STRATEGY}
          siteId="plasmodb"
          conversationId={STRATEGY.id}
        />
      </Wrapper>,
    );

    expect(screen.getByTestId("react-flow")).toBeTruthy();
  });
});

const COUNTED: Strategy = {
  ...STRATEGY,
  steps: STRATEGY.steps.map((step) => ({ ...step, estimatedSize: 5321 })),
};

const PAST_THE_DEBOUNCE_MS = 1000;

function pause(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function renderGraph(strategy: Strategy) {
  const { Wrapper, queryClient } = createTestWrapper();
  render(
    <Wrapper>
      <StrategyGraph
        strategy={strategy}
        siteId="plasmodb"
        conversationId={strategy.id}
      />
    </Wrapper>,
  );
  return queryClient;
}

describe("the canvas counts only the steps a save left without a count", () => {
  beforeEach(() => {
    vi.mocked(computeStepCounts).mockClear();
  });

  afterEach(() => {
    cleanup();
  });

  it("sends no count request when the save counted every step", async () => {
    renderGraph(COUNTED);
    await pause(PAST_THE_DEBOUNCE_MS);

    expect(vi.mocked(computeStepCounts).mock.calls).toHaveLength(0);
  });

  it("sends one count request for a step the save did not count", async () => {
    renderGraph(STRATEGY);

    await waitFor(
      () => expect(vi.mocked(computeStepCounts).mock.calls).toHaveLength(1),
      { timeout: 3000 },
    );
    expect(vi.mocked(computeStepCounts).mock.calls[0]?.[0]).toMatchObject({
      siteId: "plasmodb",
    });
  });

  it("waits for a save in flight, then counts what it left uncounted", async () => {
    let finish: () => void = () => {};
    const saving = new Promise<void>((resolve) => {
      finish = resolve;
    });
    const { Wrapper, queryClient } = createTestWrapper();
    const mutation = queryClient.getMutationCache().build(queryClient, {
      mutationKey: [...APPLY_OPERATION_MUTATION_KEY, STRATEGY.id],
      mutationFn: () => saving,
    });
    const settled = mutation.execute(undefined);
    render(
      <Wrapper>
        <StrategyGraph
          strategy={STRATEGY}
          siteId="plasmodb"
          conversationId={STRATEGY.id}
        />
      </Wrapper>,
    );
    await pause(PAST_THE_DEBOUNCE_MS);

    expect(vi.mocked(computeStepCounts).mock.calls).toHaveLength(0);

    await act(async () => {
      finish();
      await settled;
    });

    await waitFor(
      () => expect(vi.mocked(computeStepCounts).mock.calls).toHaveLength(1),
      { timeout: 3000 },
    );
  });
});
