// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";

const fitViewMock = vi.fn();
const zoomInMock = vi.fn();
const zoomOutMock = vi.fn();

vi.mock("@xyflow/react", async () => {
  const React = await import("react");
  return {
    ReactFlowProvider: ({ children }: { children: ReactNode }) =>
      React.createElement("div", { "data-testid": "rf-provider" }, children),
    useReactFlow: () => ({
      fitView: fitViewMock,
      zoomIn: zoomInMock,
      zoomOut: zoomOutMock,
    }),
  };
});

import { CanvasControls } from "./CanvasControls";

describe("CanvasControls", () => {
  afterEach(() => {
    cleanup();
    fitViewMock.mockReset();
    zoomInMock.mockReset();
    zoomOutMock.mockReset();
  });

  it("renders all four buttons", () => {
    const onRelayout = vi.fn();
    render(<CanvasControls onRelayout={onRelayout} />);
    expect(screen.getByRole("button", { name: /tidy layout/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /fit/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /zoom in/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /zoom out/i })).toBeTruthy();
  });

  it("Tidy layout fires the supplied callback", () => {
    const onRelayout = vi.fn();
    render(<CanvasControls onRelayout={onRelayout} />);
    fireEvent.click(screen.getByRole("button", { name: /tidy layout/i }));
    expect(onRelayout).toHaveBeenCalled();
  });

  it("Fit triggers ReactFlow fitView", () => {
    render(<CanvasControls onRelayout={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /fit/i }));
    expect(fitViewMock).toHaveBeenCalled();
  });

  it("Zoom buttons trigger zoomIn / zoomOut", () => {
    render(<CanvasControls onRelayout={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /zoom in/i }));
    fireEvent.click(screen.getByRole("button", { name: /zoom out/i }));
    expect(zoomInMock).toHaveBeenCalled();
    expect(zoomOutMock).toHaveBeenCalled();
  });
});
