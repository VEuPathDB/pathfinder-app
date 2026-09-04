// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { cleanup, render } from "@testing-library/react";

interface ReactFlowProps {
  colorMode?: string;
  children?: ReactNode;
}

const reactFlowProps: ReactFlowProps[] = [];
const backgroundProps: { color?: string }[] = [];

vi.mock("@xyflow/react", async () => {
  const React = await import("react");
  return {
    ReactFlow: (props: ReactFlowProps) => {
      reactFlowProps.push(props);
      return React.createElement("div", { "data-testid": "rf" }, props.children);
    },
    Background: (props: { color?: string }) => {
      backgroundProps.push(props);
      return React.createElement("div", { "data-testid": "rf-background" });
    },
    Panel: ({ children }: { children?: ReactNode }) =>
      React.createElement("div", null, children),
    ConnectionMode: { Loose: "loose" },
    SelectionMode: { Partial: "partial" },
    MarkerType: { ArrowClosed: "arrowclosed" },
    Position: { Left: "left", Right: "right" },
    Handle: () => null,
    NodeToolbar: () => null,
    useStore: () => "0|0|1",
  };
});

const ctx = {
  nodes: [],
  edges: [],
  strategy: null,
  editableSteps: [],
  isCompact: true,
  selectedNodeIds: [],
  onNodesChange: () => {},
  onEdgesChange: () => {},
  handleNodesDelete: () => {},
  handleNodeDragStop: () => {},
  handleConnect: () => {},
  isValidConnection: () => true,
  handleMoveStart: () => {},
  setEdgeMenu: () => {},
  handleSelectionChange: () => {},
  setSelectedStep: () => {},
  requestDeleteMany: () => {},
  handleRelayout: () => {},
  handleStartCombineFromSelection: () => {},
  handleStartOrthologTransformFromSelection: () => {},
  combineMismatchGroups: [],
};

vi.mock("@/features/strategy/graph/StrategyGraphContext", () => ({
  useStrategyGraphCtx: () => ctx,
}));

import { StrategyGraphLayout } from "./StrategyGraphLayout";

describe("StrategyGraphLayout ground", () => {
  afterEach(() => {
    cleanup();
    reactFlowProps.length = 0;
    backgroundProps.length = 0;
    document.documentElement.removeAttribute("data-theme");
  });

  it("paints the canvas grid from the border token", () => {
    render(<StrategyGraphLayout />);
    expect(backgroundProps[0]?.color).toBe("hsl(var(--border))");
  });

  it("runs light when the document declares no ground", () => {
    render(<StrategyGraphLayout />);
    expect(reactFlowProps[0]?.colorMode).toBe("light");
  });

  it("follows the document onto a dark ground", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    render(<StrategyGraphLayout />);
    expect(reactFlowProps[0]?.colorMode).toBe("dark");
  });
});
