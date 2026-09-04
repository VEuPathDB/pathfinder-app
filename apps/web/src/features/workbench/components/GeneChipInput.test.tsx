// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { GeneSet } from "@pathfinder/shared";

const storeState: Record<string, unknown> = {
  geneSets: [] as GeneSet[],
};

vi.mock("@/state/useSessionStore", () => ({
  useSessionStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      selectedSite: "PlasmoDB",
    }),
}));

vi.mock("@/features/workbench/hooks/useGeneSetsQuery", () => ({
  useGeneSetsQuery: () => ({
    data: storeState["geneSets"] as GeneSet[],
    isPending: false,
  }),
}));

const mockSearchGenes = vi.fn();
const mockResolveGeneIds = vi.fn();
vi.mock("@pathfinder/shared/generated/hooks/useSearchGenes", () => ({
  searchGenes: (...args: unknown[]) => mockSearchGenes(...args),
}));

vi.mock("@pathfinder/shared/generated/hooks/useResolveGenes", () => ({
  resolveGenes: (...args: unknown[]) => mockResolveGeneIds(...args),
}));

import { GeneChipInput } from "./GeneChipInput";

describe("GeneChipInput", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders chips for each gene ID", () => {
    render(
      <GeneChipInput
        siteId="PlasmoDB"
        value={["PF3D7_0100100", "PF3D7_0200200"]}
        onChange={() => {}}
        label="Positive Controls"
      />,
    );
    expect(screen.getByText("PF3D7_0100100")).toBeTruthy();
    expect(screen.getByText("PF3D7_0200200")).toBeTruthy();
  });

  it("renders label", () => {
    render(
      <GeneChipInput
        siteId="PlasmoDB"
        value={[]}
        onChange={() => {}}
        label="Positive Controls"
      />,
    );
    expect(screen.getByText("Positive Controls")).toBeTruthy();
  });

  it("shows required marker when required", () => {
    render(
      <GeneChipInput
        siteId="PlasmoDB"
        value={[]}
        onChange={() => {}}
        label="Positive Controls"
        required
      />,
    );
    expect(screen.getByText("*")).toBeTruthy();
  });

  it("removes a chip when X is clicked", () => {
    const onChange = vi.fn();
    render(
      <GeneChipInput
        siteId="PlasmoDB"
        value={["PF3D7_0100100", "PF3D7_0200200"]}
        onChange={onChange}
        label="Controls"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Remove PF3D7_0100100" }));
    expect(onChange).toHaveBeenCalledWith(["PF3D7_0200200"]);
  });

  it("renders action buttons (From Gene Set, Import)", () => {
    render(
      <GeneChipInput
        siteId="PlasmoDB"
        value={[]}
        onChange={() => {}}
        label="Controls"
      />,
    );
    expect(screen.getByText(/From Gene Set/)).toBeTruthy();
    expect(screen.getByText(/Import/)).toBeTruthy();
  });

  it("renders search input for autocomplete", () => {
    render(
      <GeneChipInput
        siteId="PlasmoDB"
        value={[]}
        onChange={() => {}}
        label="Controls"
      />,
    );
    expect(screen.getByPlaceholderText("Search genes...")).toBeTruthy();
  });

  it("auto-verifies genes after adding", async () => {
    mockResolveGeneIds.mockResolvedValue({
      resolved: [
        {
          geneId: "PF3D7_0100100",
          displayName: "PF3D7_0100100",
          organism: "Plasmodium falciparum 3D7",
          product: "test",
          geneName: "",
          geneType: "",
          location: "",
        },
      ],
      unresolved: ["INVALID_001"],
    });

    render(
      <GeneChipInput
        siteId="PlasmoDB"
        value={["PF3D7_0100100", "INVALID_001"]}
        onChange={() => {}}
        label="Controls"
      />,
    );

    // Auto-verification fires after debounce
    await waitFor(
      () => {
        expect(mockResolveGeneIds).toHaveBeenCalledWith("PlasmoDB", {
          geneIds: ["PF3D7_0100100", "INVALID_001"],
        });
      },
      { timeout: 2000 },
    );
  });

  it("shows gene count", () => {
    const { container } = render(
      <GeneChipInput
        siteId="PlasmoDB"
        value={["PF3D7_0100100", "PF3D7_0200200", "PF3D7_0300300"]}
        onChange={() => {}}
        label="Controls"
      />,
    );
    expect(container.querySelectorAll("[data-gene-chip]")).toHaveLength(3);
  });
});
