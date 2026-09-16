// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { GeneSet } from "@pathfinder/shared";
import { CompareModal } from "./CompareModal";

function geneSet(over: Partial<GeneSet> = {}): GeneSet {
  return {
    id: "gs1",
    name: "Set A",
    siteId: "plasmodb",
    geneIds: ["G1", "G2"],
    source: "paste",
    geneCount: 2,
    membershipDigest: "0000000000000001",
    createdAt: "2026-01-01T00:00:00.000Z",
    ...over,
  };
}

describe("CompareModal", () => {
  it("draws the three-way legend from the chart tokens", () => {
    render(
      <CompareModal
        open
        onClose={() => {}}
        setA={geneSet()}
        setB={geneSet({ id: "gs2", name: "Set B", geneIds: ["G2", "G3"] })}
      />,
    );

    const headings = screen.getAllByRole("heading", { level: 4 });
    expect(headings).toHaveLength(3);
    expect(headings[0]).toHaveTextContent("Only in Set A");
    expect(headings[1]).toHaveTextContent("Shared");
    expect(headings[2]).toHaveTextContent("Only in Set B");

    expect(headings[0]?.querySelector("span")).toHaveClass("bg-[hsl(var(--chart-1))]");
    expect(headings[1]?.querySelector("span")).toHaveClass("bg-[hsl(var(--chart-2))]");
    expect(headings[2]?.querySelector("span")).toHaveClass("bg-[hsl(var(--chart-3))]");
  });
});
