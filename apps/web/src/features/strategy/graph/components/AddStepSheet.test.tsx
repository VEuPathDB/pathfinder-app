// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { Search } from "@pathfinder/shared";
import type * as SitesApi from "@/lib/api/sites";
import { createTestWrapper } from "@/lib/query/testing";

const SEARCHES: Search[] = [
  {
    name: "GenesByTaxon",
    displayName: "Genes by Taxon",
    description: "",
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

vi.mock("@/features/strategy/mutations", () => ({
  useAddStepMutation: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
  }),
}));

import { AddStepSheet } from "./AddStepSheet";

describe("AddStepSheet", () => {
  afterEach(() => cleanup());

  it("renders the search picker (Combobox)", async () => {
    const { Wrapper } = createTestWrapper();
    render(
      <Wrapper>
        <AddStepSheet
          open
          onOpenChange={vi.fn()}
          siteId="plasmodb"
          recordType="gene"
          conversationId="strategy-1"
        />
      </Wrapper>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("add-step-sheet")).toBeTruthy();
    });
    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeTruthy();
    });
  });

  it("Add step button is disabled until a search is selected", async () => {
    const { Wrapper } = createTestWrapper();
    render(
      <Wrapper>
        <AddStepSheet
          open
          onOpenChange={vi.fn()}
          siteId="plasmodb"
          recordType="gene"
          conversationId="strategy-1"
        />
      </Wrapper>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("add-step-sheet")).toBeTruthy();
    });
    const btn = screen.getByRole<HTMLButtonElement>("button", {
      name: /add step/i,
    });
    expect(btn.disabled).toBe(true);
  });
});
