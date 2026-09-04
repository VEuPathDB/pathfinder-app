// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";

interface MiniMapProps {
  nodeColor?: (node: unknown) => string;
  maskColor?: string;
}

const miniMapProps: MiniMapProps[] = [];

vi.mock("@xyflow/react", async () => {
  const React = await import("react");
  return {
    ReactFlowProvider: ({ children }: { children: ReactNode }) =>
      React.createElement("div", null, children),
    MiniMap: (props: MiniMapProps) => {
      miniMapProps.push(props);
      return React.createElement("div", { "data-testid": "minimap-stub" });
    },
    useStore: () => "0|0|1",
  };
});

vi.mock("@/features/strategy/graph/hooks/useCanvasIdle", () => ({
  useCanvasIdle: () => false,
}));

import { SmartMiniMap, minimapNodeColor } from "./SmartMiniMap";

function setTokens(): void {
  const root = document.documentElement;
  root.style.setProperty("--kind-leaf", "160 60% 45%");
  root.style.setProperty("--kind-combine", "200 80% 55%");
  root.style.setProperty("--kind-transform", "270 60% 55%");
  root.style.setProperty("--muted-foreground", "215 16% 40%");
}

describe("SmartMiniMap", () => {
  afterEach(() => {
    cleanup();
    miniMapProps.length = 0;
    document.documentElement.removeAttribute("style");
  });

  it("returns null when nodeCount <= 8", () => {
    const { container } = render(<SmartMiniMap nodeCount={8} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders MiniMap when nodeCount > 8", () => {
    render(<SmartMiniMap nodeCount={9} />);
    expect(screen.getByTestId("smart-mini-map")).toBeTruthy();
    expect(screen.getByTestId("minimap-stub")).toBeTruthy();
  });

  it("masks with the foreground token instead of a black literal", () => {
    render(<SmartMiniMap nodeCount={9} />);
    expect(miniMapProps[0]?.maskColor).toBe("hsl(var(--foreground) / 0.1)");
  });

  it("paints each node kind with its resolved kind token", () => {
    setTokens();
    expect(minimapNodeColor({ data: { step: { kind: "search" } } })).toBe(
      "hsl(160 60% 45%)",
    );
    expect(minimapNodeColor({ data: { step: { kind: "combine" } } })).toBe(
      "hsl(200 80% 55%)",
    );
    expect(minimapNodeColor({ data: { step: { kind: "transform" } } })).toBe(
      "hsl(270 60% 55%)",
    );
  });

  it("falls back to the muted-foreground token for an unknown kind", () => {
    setTokens();
    expect(minimapNodeColor({ data: { step: { kind: "mystery" } } })).toBe(
      "hsl(215 16% 40%)",
    );
    expect(minimapNodeColor({})).toBe("hsl(215 16% 40%)");
  });

  it("paints currentColor when the stylesheet defines nothing", () => {
    expect(minimapNodeColor({ data: { step: { kind: "search" } } })).toBe(
      "currentColor",
    );
  });
});
