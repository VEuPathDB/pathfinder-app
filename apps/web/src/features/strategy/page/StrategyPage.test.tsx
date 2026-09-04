/**
 * @vitest-environment jsdom
 */
import type * as ReactQueryModule from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { chatRoot } from "@/lib/routes";

type ReactQueryExports = typeof ReactQueryModule;

const STRATEGY = {
  id: "conv-1",
  name: "Test strategy",
  siteId: "plasmodb",
  recordType: "gene",
  steps: [
    {
      id: "step_1",
      kind: "search",
      displayName: "Genes by taxon",
      searchName: "GenesByTaxon",
      recordType: "gene",
      parameters: {},
      isFiltered: false,
    },
  ],
  rootStepId: "step_1",
  isSaved: false,
  description: null,
  wdkStrategyId: null,
  wdkUrl: null,
  createdAt: "2026-04-22T00:00:00Z",
  updatedAt: "2026-04-22T00:00:00Z",
};

interface StrategyGraphSpyProps {
  siteId: string;
  showTopbar?: boolean;
  focusStepId?: string | null;
  strategy: { id?: string } | null;
}

beforeEach(() => {
  vi.resetModules();
});

describe("StrategyPage", () => {
  it("renders the StrategyGraph with hydrated strategy + siteId, no focused step", async () => {
    const graphSpy = vi.fn();
    vi.doMock("next/navigation", () => ({
      redirect: vi.fn(),
    }));
    vi.doMock("@tanstack/react-query", async () => {
      const actual = await vi.importActual<ReactQueryExports>("@tanstack/react-query");
      return {
        ...actual,
        useQuery: () => ({
          data: STRATEGY,
          isFetched: true,
          isPending: false,
        }),
      };
    });
    vi.doMock("@/features/strategy/graph/components/StrategyGraph", () => ({
      StrategyGraph: (props: StrategyGraphSpyProps) => {
        graphSpy(props);
        return <div data-testid="strategy-graph" />;
      },
    }));

    const { StrategyPage } = await import("./StrategyPage");
    const { useStrategyStore } = await import("@/state/strategy/store");
    const { render, screen } = await import("@testing-library/react");

    useStrategyStore.getState().clear();

    render(
      <StrategyPage siteId="plasmodb" conversationId="conv-1" focusStepId={null} />,
    );

    expect(screen.getByTestId("strategy-graph")).toBeTruthy();
    const lastCall = graphSpy.mock.calls.at(-1);
    if (lastCall === undefined) throw new Error("graph not rendered");
    const props = lastCall[0] as StrategyGraphSpyProps;
    expect(props.strategy?.id).toBe("conv-1");
    expect(props.siteId).toBe("plasmodb");
    expect(props.showTopbar).toBe(true);
    expect(props.focusStepId).toBe(null);
  });

  it("forwards focusStepId to the StrategyGraph", async () => {
    const graphSpy = vi.fn();
    vi.doMock("next/navigation", () => ({
      redirect: vi.fn(),
    }));
    vi.doMock("@tanstack/react-query", async () => {
      const actual = await vi.importActual<ReactQueryExports>("@tanstack/react-query");
      return {
        ...actual,
        useQuery: () => ({
          data: STRATEGY,
          isFetched: true,
          isPending: false,
        }),
      };
    });
    vi.doMock("@/features/strategy/graph/components/StrategyGraph", () => ({
      StrategyGraph: (props: StrategyGraphSpyProps) => {
        graphSpy(props);
        return <div data-testid="strategy-graph" />;
      },
    }));

    const { StrategyPage } = await import("./StrategyPage");
    const { useStrategyStore } = await import("@/state/strategy/store");
    const { render } = await import("@testing-library/react");

    useStrategyStore.getState().clear();

    render(
      <StrategyPage siteId="plasmodb" conversationId="conv-1" focusStepId="step_1" />,
    );

    const lastCall = graphSpy.mock.calls.at(-1);
    if (lastCall === undefined) throw new Error("graph not rendered");
    const props = lastCall[0] as StrategyGraphSpyProps;
    expect(props.focusStepId).toBe("step_1");
  });

  it("redirects to /[siteId]/conversation when the conversation does not exist", async () => {
    const redirectSpy = vi.fn();
    vi.doMock("next/navigation", () => ({
      redirect: redirectSpy,
    }));
    vi.doMock("@tanstack/react-query", async () => {
      const actual = await vi.importActual<ReactQueryExports>("@tanstack/react-query");
      return {
        ...actual,
        useQuery: () => ({
          data: null,
          isFetched: true,
          isPending: false,
        }),
      };
    });
    vi.doMock("@/features/strategy/graph/components/StrategyGraph", () => ({
      StrategyGraph: () => <div />,
    }));

    const { StrategyPage } = await import("./StrategyPage");
    const { useStrategyStore } = await import("@/state/strategy/store");
    const { render } = await import("@testing-library/react");

    useStrategyStore.getState().clear();

    render(
      <StrategyPage siteId="plasmodb" conversationId="missing" focusStepId={null} />,
    );

    expect(redirectSpy).toHaveBeenCalledWith(chatRoot("plasmodb"));
  });

  it("renders a spinner while the conversation query is pending", async () => {
    vi.doMock("next/navigation", () => ({
      redirect: vi.fn(),
    }));
    vi.doMock("@tanstack/react-query", async () => {
      const actual = await vi.importActual<ReactQueryExports>("@tanstack/react-query");
      return {
        ...actual,
        useQuery: () => ({
          data: undefined,
          isFetched: false,
          isPending: true,
        }),
      };
    });
    vi.doMock("@/features/strategy/graph/components/StrategyGraph", () => ({
      StrategyGraph: () => <div data-testid="strategy-graph" />,
    }));

    const { StrategyPage } = await import("./StrategyPage");
    const { useStrategyStore } = await import("@/state/strategy/store");
    const { render, screen } = await import("@testing-library/react");

    useStrategyStore.getState().clear();

    const { container } = render(
      <StrategyPage siteId="plasmodb" conversationId="conv-1" focusStepId={null} />,
    );

    expect(screen.queryAllByTestId("strategy-graph")).toHaveLength(0);
    expect(container.querySelectorAll("svg.animate-spin")).toHaveLength(1);
  });
});
