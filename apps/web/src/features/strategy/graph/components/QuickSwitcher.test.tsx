// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { Step, Strategy } from "@pathfinder/shared";

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn(), back: vi.fn() }),
}));

import { strategyStepUrl } from "@/lib/routes";
import { QuickSwitcher } from "./QuickSwitcher";

function makeStep(id: string, displayName: string, searchName: string): Step {
  return {
    id,
    kind: "search",
    displayName,
    searchName,
    parameters: {},
  };
}

function makeStrategy(steps: Step[]): Strategy {
  return {
    id: "conv-42",
    name: "Test",
    rootStepId: steps.at(-1)?.id ?? "",
    recordType: "gene",
    steps,
    siteId: "plasmodb",
    isSaved: false,
    createdAt: "2026-01-01T00:00:00.000Z",
    updatedAt: "2026-01-01T00:00:00.000Z",
  };
}

describe("QuickSwitcher", () => {
  afterEach(() => {
    cleanup();
    pushMock.mockReset();
  });

  it("renders steps when open", () => {
    const strategy = makeStrategy([
      makeStep("a", "Genes by ID", "GenesByLocusTag"),
      makeStep("b", "Combine intersect", "CombineSearches"),
    ]);
    render(<QuickSwitcher open={true} onOpenChange={vi.fn()} strategy={strategy} />);
    expect(screen.getByText("Genes by ID")).toBeInTheDocument();
    expect(screen.getByText("Combine intersect")).toBeInTheDocument();
  });

  it("filters by name", () => {
    const strategy = makeStrategy([
      makeStep("a", "Genes by ID", "GenesByLocusTag"),
      makeStep("b", "Combine intersect", "CombineSearches"),
    ]);
    render(<QuickSwitcher open={true} onOpenChange={vi.fn()} strategy={strategy} />);
    const input = screen.getByLabelText(/search steps/i);
    fireEvent.change(input, { target: { value: "intersect" } });
    expect(screen.queryByText("Genes by ID")).toBeNull();
    expect(screen.getByText("Combine intersect")).toBeInTheDocument();
  });

  it("filters by searchName", () => {
    const strategy = makeStrategy([
      makeStep("a", "Genes by ID", "GenesByLocusTag"),
      makeStep("b", "Combine intersect", "CombineSearches"),
    ]);
    render(<QuickSwitcher open={true} onOpenChange={vi.fn()} strategy={strategy} />);
    const input = screen.getByLabelText(/search steps/i);
    fireEvent.change(input, { target: { value: "LocusTag" } });
    expect(screen.getByText("Genes by ID")).toBeInTheDocument();
    expect(screen.queryByText("Combine intersect")).toBeNull();
  });

  it("selecting an item navigates and closes", () => {
    const onOpenChange = vi.fn();
    const strategy = makeStrategy([makeStep("a", "Genes by ID", "GenesByLocusTag")]);
    render(
      <QuickSwitcher open={true} onOpenChange={onOpenChange} strategy={strategy} />,
    );
    fireEvent.click(screen.getByText("Genes by ID"));
    expect(pushMock).toHaveBeenCalledWith(strategyStepUrl("conv-42", "a"));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
