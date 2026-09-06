/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";

import { runCustomEnrichment } from "@/features/workbench/analysis/api/compute";
import { CustomEnrichmentSection } from "./CustomEnrichmentSection";

vi.mock("@/features/workbench/analysis/api/compute", () => ({
  runCustomEnrichment: vi.fn(),
}));

const mockRun = vi.mocked(runCustomEnrichment);

function withClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

async function runWith(
  geneSetSize: number,
  geneSetInBackground: number,
  oddsRatio: number | null = 29.3333,
) {
  mockRun.mockResolvedValue({
    geneSetName: "kinase panel",
    geneSetSize,
    geneSetInBackground,
    overlapCount: 8,
    overlapGenes: ["PF3D7_0100100"],
    backgroundSize: 200,
    tpCount: 8,
    foldEnrichment: 6.6667,
    pValue: 8.991416145071992e-7,
    oddsRatio,
  });

  withClient(<CustomEnrichmentSection experimentId="exp-1" />);

  await userEvent.type(screen.getByPlaceholderText(/Gene set name/i), "kinase panel");
  await userEvent.type(screen.getByPlaceholderText(/Paste gene IDs/i), "PF3D7_0100100");
  await userEvent.click(screen.getByRole("button", { name: /Fisher/i }));
}

describe("CustomEnrichmentSection", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("reports the pasted size and how much of it is in the background", async () => {
    await runWith(250, 5);

    await waitFor(() => {
      expect(screen.getByText(/Gene set size:/)).toHaveTextContent(
        "Gene set size: 250 (5 in background)",
      );
    });
  });

  it("still reports both numbers when the whole set is in the background", async () => {
    await runWith(12, 12);

    await waitFor(() => {
      expect(screen.getByText(/Gene set size:/)).toHaveTextContent(
        "Gene set size: 12 (12 in background)",
      );
    });
  });

  it("shows an unbounded odds ratio as Inf", async () => {
    await runWith(20, 20, null);

    await waitFor(() => {
      expect(screen.getByText(/Odds Ratio:/)).toHaveTextContent("Odds Ratio: Inf");
    });
  });

  it("shows a finite odds ratio as a number", async () => {
    await runWith(12, 12);

    await waitFor(() => {
      expect(screen.getByText(/Odds Ratio:/)).toHaveTextContent("Odds Ratio: 29.33");
    });
  });
});
