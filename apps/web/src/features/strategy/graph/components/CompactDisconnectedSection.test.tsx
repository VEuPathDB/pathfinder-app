// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { Step } from "@strategist/shared";
import { CompactDisconnectedSection } from "./CompactDisconnectedSection";

const ORPHAN: Step = {
  id: "step_9",
  kind: "search",
  displayName: "Genes by taxon",
  searchName: "GenesByTaxon",
  recordType: "gene",
  parameters: {},
  isFiltered: false,
};

describe("CompactDisconnectedSection", () => {
  it("paints the disconnected frame and header from the warning token", () => {
    render(<CompactDisconnectedSection orphans={[ORPHAN]} />);
    const section = screen.getByTestId("compact-strategy-orphans");
    expect(section).toHaveClass("border-warning/40", "bg-warning/10");
    expect(section.className).not.toContain("amber");
    expect(section.querySelector("header")).toHaveClass("text-warning");
    expect(section.innerHTML).not.toContain("amber");
  });

  it("lists each disconnected step", () => {
    render(<CompactDisconnectedSection orphans={[ORPHAN]} />);
    expect(screen.getByText("1 disconnected")).toBeInTheDocument();
    expect(screen.getByTestId("compact-orphan-row-step_9")).toBeInTheDocument();
  });
});
