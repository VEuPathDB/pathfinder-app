// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import type { GeneSet } from "@pathfinder/shared";

const geneSetsState: { geneSets: GeneSet[] } = {
  geneSets: [],
};

vi.mock("@/state/useSessionStore", () => ({
  useSessionStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      selectedSite: "PlasmoDB",
    }),
}));

vi.mock("@/features/workbench/hooks/useGeneSetsQuery", () => ({
  useGeneSetsQuery: () => ({
    data: geneSetsState.geneSets,
    isPending: false,
  }),
}));

import { GeneSetPicker } from "./GeneSetPicker";

function setStoreGeneSets(geneSets: GeneSet[]) {
  geneSetsState.geneSets = geneSets;
}

describe("GeneSetPicker", () => {
  afterEach(cleanup);

  it("renders button with gene set count", () => {
    setStoreGeneSets([
      {
        id: "1",
        name: "Set A",
        geneIds: ["g1", "g2"],
        geneCount: 2,
        membershipDigest: "0000000000000009",
        source: "paste",
        stepCount: 1,
        createdAt: "2026-01-01T00:00:00Z",
        siteId: "PlasmoDB",
      },
      {
        id: "2",
        name: "Set B",
        geneIds: ["g3"],
        geneCount: 1,
        membershipDigest: "0000000000000008",
        source: "strategy",
        stepCount: 1,
        createdAt: "2026-01-01T00:00:00Z",
        siteId: "PlasmoDB",
      },
    ]);
    render(<GeneSetPicker onSelect={() => {}} />);
    expect(screen.getByText(/From Gene Set/)).toBeTruthy();
  });

  it("opens dropdown and shows gene sets", () => {
    setStoreGeneSets([
      {
        id: "1",
        name: "Apicoplast kinases",
        geneIds: ["g1", "g2"],
        geneCount: 2,
        membershipDigest: "0000000000000007",
        source: "paste",
        stepCount: 1,
        createdAt: "2026-01-01T00:00:00Z",
        siteId: "PlasmoDB",
      },
    ]);
    render(<GeneSetPicker onSelect={() => {}} />);
    fireEvent.click(screen.getByText(/From Gene Set/));
    expect(screen.getByText("Apicoplast kinases")).toBeTruthy();
    expect(screen.getByText("2 genes")).toBeTruthy();
  });

  it("calls onSelect with gene IDs when a set is clicked", () => {
    const onSelect = vi.fn();
    setStoreGeneSets([
      {
        id: "1",
        name: "Set A",
        geneIds: ["PF3D7_0100100", "PF3D7_0200200"],
        geneCount: 2,
        membershipDigest: "0000000000000006",
        source: "paste",
        stepCount: 1,
        createdAt: "2026-01-01T00:00:00Z",
        siteId: "PlasmoDB",
      },
    ]);
    render(<GeneSetPicker onSelect={onSelect} />);
    fireEvent.click(screen.getByText(/From Gene Set/));
    fireEvent.click(screen.getByText("Set A"));
    expect(onSelect).toHaveBeenCalledWith(["PF3D7_0100100", "PF3D7_0200200"]);
  });

  it("is disabled when no gene sets have gene IDs", () => {
    setStoreGeneSets([
      {
        id: "1",
        name: "Empty",
        geneIds: [],
        geneCount: 0,
        membershipDigest: "0000000000000005",
        source: "strategy",
        stepCount: 1,
        createdAt: "2026-01-01T00:00:00Z",
        siteId: "PlasmoDB",
      },
    ]);
    render(<GeneSetPicker onSelect={() => {}} />);
    const btn = screen.getByText(/From Gene Set/).closest("button");
    expect(btn?.hasAttribute("disabled")).toBe(true);
  });
});
