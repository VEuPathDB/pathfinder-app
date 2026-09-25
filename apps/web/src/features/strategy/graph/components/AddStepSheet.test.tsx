// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { RecordType, Search } from "@pathfinder/shared";
import type * as SitesApi from "@/lib/api/sites";
import { createTestWrapper } from "@/lib/query/testing";

const SEARCHES: Search[] = [
  {
    name: "GenesByTaxon",
    displayName: "Genes by Taxon",
    description: "",
    recordType: "transcript",
  },
];

const RECORD_TYPES: RecordType[] = [{ name: "transcript", displayName: "Genes" }];

vi.mock("@/lib/api/sites", async () => {
  const actual = await vi.importActual<typeof SitesApi>("@/lib/api/sites");
  return {
    ...actual,
    searchesOptions: () => ({
      queryKey: ["sites", "x", "searches", "gene"],
      queryFn: async () => SEARCHES,
      enabled: true,
    }),
    recordTypesOptions: () => ({
      queryKey: ["sites", "x", "record-types"],
      queryFn: async () => RECORD_TYPES,
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

  it("heads each group of searches with the record type's display name", async () => {
    const { Wrapper } = createTestWrapper();
    render(
      <Wrapper>
        <AddStepSheet
          open
          onOpenChange={vi.fn()}
          siteId="plasmodb"
          recordType="transcript"
          conversationId="strategy-1"
        />
      </Wrapper>,
    );
    await userEvent.click(await screen.findByRole("combobox"));

    expect(await screen.findByText("Genes")).toBeVisible();
    expect(screen.queryByText("transcript")).toBeNull();
  });
});
