// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { GeneSet } from "@pathfinder/shared";
import { OverlapModal } from "./OverlapModal";

function geneSet(over: Partial<GeneSet> = {}): GeneSet {
  return {
    id: "gs1",
    name: "Kinases",
    siteId: "plasmodb",
    geneIds: ["PF3D7_0100100"],
    source: "paste",
    geneCount: 1,
    membershipDigest: "000000000000000a",
    createdAt: "2026-01-01T00:00:00.000Z",
    ...over,
  };
}

describe("OverlapModal", () => {
  it("warns about unresolved strategy-backed sets through the warning token", () => {
    render(
      <OverlapModal
        open
        onClose={() => {}}
        sets={[
          geneSet(),
          geneSet({
            id: "gs2",
            name: "Unresolved",
            geneIds: [],
            geneCount: 0,
            source: "strategy",
            wdkStepId: 12345,
          }),
        ]}
      />,
    );
    const notice = screen.getByText(/Overlap cannot be computed/);
    expect(notice).toHaveClass("border-warning/40", "bg-warning/10", "text-warning");
    expect(notice.className).not.toContain("yellow");
  });
});
