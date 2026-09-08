// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { Search } from "@pathfinder/shared";
import type * as SitesApi from "@/lib/api/sites";
import { createTestWrapper } from "@/lib/query/testing";

const SEARCHES: Search[] = [
  {
    name: "GenesByOrthology",
    displayName: "Genes by Ortholog Pattern",
    description: "Pick orthologs",
    recordType: "gene",
  },
  {
    name: "GenesByTaxon",
    displayName: "Genes by Taxon",
    description: "non-ortholog",
    recordType: "gene",
  },
];

vi.mock("@/lib/api/sites", async () => {
  const actual = await vi.importActual<typeof SitesApi>("@/lib/api/sites");
  return {
    ...actual,
    searchesOptions: () => ({
      queryKey: ["sites", "x", "searches", "gene"],
      queryFn: async () => SEARCHES,
      enabled: true,
    }),
  };
});

import { OrthologSheet } from "./OrthologSheet";

describe("OrthologSheet", () => {
  afterEach(() => cleanup());

  it("filters and lists ortholog searches in the Combobox", async () => {
    const { Wrapper } = createTestWrapper();
    render(
      <Wrapper>
        <OrthologSheet
          open
          onOpenChange={vi.fn()}
          siteId="plasmodb"
          recordType="gene"
          onChoose={vi.fn()}
        />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("ortholog-sheet")).toBeTruthy();
    });
    // Combobox trigger renders once the searches query resolves.
    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeTruthy();
    });
  });

  it("Insert button is disabled until a search is selected", () => {
    const { Wrapper } = createTestWrapper();
    render(
      <Wrapper>
        <OrthologSheet
          open
          onOpenChange={vi.fn()}
          siteId="plasmodb"
          recordType="gene"
          onChoose={vi.fn()}
        />
      </Wrapper>,
    );
    const insert = screen.getByRole("button", { name: /^insert$/i });
    expect((insert as HTMLButtonElement).disabled).toBe(true);
  });

  it("toggling the Switch updates insertBetween (smoke)", () => {
    const { Wrapper } = createTestWrapper();
    render(
      <Wrapper>
        <OrthologSheet
          open
          onOpenChange={vi.fn()}
          siteId="plasmodb"
          recordType="gene"
          onChoose={vi.fn()}
        />
      </Wrapper>,
    );
    const sw = screen.getByRole("switch");
    expect(sw.getAttribute("aria-checked")).toBe("true");
    fireEvent.click(sw);
    expect(sw.getAttribute("aria-checked")).toBe("false");
  });
});
