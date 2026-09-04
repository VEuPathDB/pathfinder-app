/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render as renderBare, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/components/charts/echartsRegistry", () => ({
  initChart: () => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    isDisposed: () => false,
  }),
}));

import type { ReactElement, ReactNode } from "react";

import { useEdaStore } from "@/state/eda";
import {
  ChatHelpersProvider,
  type ChatHelpers,
} from "../../runtime/chatHelpersContext";
import { DataEdaSubsetPreview } from "./DataEdaSubsetPreview";
import {
  EDA_ANALYSIS_STATE_FIXTURE,
  EDA_SUBSET_PREVIEW_FIXTURE,
} from "./edaPartFixtures";

const DISTRIBUTION = EDA_SUBSET_PREVIEW_FIXTURE.distribution;
if (DISTRIBUTION === null) throw new Error("the fixture carries a distribution");

const STUB_CHAT = { messages: [], status: "ready" } as unknown as ChatHelpers;

function ChatWrapper({ children }: { children: ReactNode }) {
  return <ChatHelpersProvider value={STUB_CHAT}>{children}</ChatHelpersProvider>;
}

function render(ui: ReactElement) {
  return renderBare(ui, { wrapper: ChatWrapper });
}

beforeEach(() => {
  useEdaStore.getState().reset();
  useEdaStore.getState().applyAnalysisState(EDA_ANALYSIS_STATE_FIXTURE);
});

describe("DataEdaSubsetPreview", () => {
  it("prints each entity count against its unfiltered total", () => {
    render(<DataEdaSubsetPreview data={EDA_SUBSET_PREVIEW_FIXTURE} />);
    expect(screen.getByTestId("data-eda-subset-preview")).toHaveTextContent(
      "6 of 12 Sample",
    );
  });

  it("captions the figure with the entity counts and the value count", () => {
    render(<DataEdaSubsetPreview data={EDA_SUBSET_PREVIEW_FIXTURE} />);
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "6 of 12 Sample, 6 values.",
    );
  });

  it("leads the caption with the sentence the model wrote", () => {
    render(
      <DataEdaSubsetPreview
        data={{
          ...EDA_SUBSET_PREVIEW_FIXTURE,
          caption: "Distribution of temperature across the febrile samples",
        }}
      />,
    );
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "Distribution of temperature across the febrile samples (6 of 12 Sample, 6 values).",
    );
  });

  it("puts the caption above the bin counts, the coverage and the notes", () => {
    render(
      <DataEdaSubsetPreview
        data={{
          ...EDA_SUBSET_PREVIEW_FIXTURE,
          distributionNote: "Temperature has 40 bins, the first 10 are shown",
          distribution: { ...DISTRIBUTION, isMultiValued: true, numVarValues: 9 },
        }}
      />,
    );
    const caption = screen.getByTestId("figure-caption");
    const below = [
      screen.getByTestId("data-eda-subset-bin-0"),
      screen.getByTestId("data-eda-subset-coverage"),
      screen.getByTestId("data-eda-subset-multivalued"),
      screen.getByTestId("data-eda-subset-note"),
    ];
    for (const node of below) {
      expect(
        caption.compareDocumentPosition(node) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeGreaterThan(0);
    }
  });

  it("keeps the histogram itself above the caption", () => {
    render(<DataEdaSubsetPreview data={EDA_SUBSET_PREVIEW_FIXTURE} />);
    const caption = screen.getByTestId("figure-caption");
    const plot = screen.getByTestId("data-eda-subset-histogram");
    expect(
      caption.compareDocumentPosition(plot) & Node.DOCUMENT_POSITION_PRECEDING,
    ).toBeGreaterThan(0);
  });

  it("titles the figure with the distribution variable", () => {
    render(<DataEdaSubsetPreview data={EDA_SUBSET_PREVIEW_FIXTURE} />);
    const title = screen.getByText("Temperature");
    expect(title.tagName).toBe("FIGCAPTION");
  });

  it("drops the value clause when the part carries no distribution", () => {
    render(
      <DataEdaSubsetPreview
        data={{ ...EDA_SUBSET_PREVIEW_FIXTURE, distribution: null }}
      />,
    );
    expect(screen.getByTestId("figure-caption").textContent).toBe("6 of 12 Sample.");
  });

  it("draws no divider, no card and no outer margin", () => {
    render(<DataEdaSubsetPreview data={EDA_SUBSET_PREVIEW_FIXTURE} />);
    expect(screen.getByTestId("figure").className).toBe("");
    expect(screen.getByTestId("data-eda-subset-preview").className).not.toMatch(
      /\bborder\b|\brounded-md\b|\bbg-card\b/,
    );
  });

  it("draws the distribution as a mini histogram named after the variable", () => {
    render(<DataEdaSubsetPreview data={EDA_SUBSET_PREVIEW_FIXTURE} />);
    expect(screen.getByTestId("data-eda-subset-histogram")).toHaveAttribute(
      "aria-label",
      "Temperature distribution over the subset",
    );
  });

  it("prints every bin label against its value", () => {
    render(<DataEdaSubsetPreview data={EDA_SUBSET_PREVIEW_FIXTURE} />);
    const bins = screen.getAllByTestId(/^data-eda-subset-bin-/);
    expect(bins).toHaveLength(2);
    expect(bins[0]).toHaveTextContent("[37, 38) 6");
    expect(bins[1]).toHaveTextContent("[41, 42] 6");
  });

  it("holds the bin counts and the coverage line in a closed disclosure", () => {
    render(<DataEdaSubsetPreview data={EDA_SUBSET_PREVIEW_FIXTURE} />);
    const summary = screen.getByText("Bin counts");
    expect(summary.tagName).toBe("SUMMARY");
    const details = summary.closest("details");
    expect(details?.open).toBe(false);
    expect(details).toContainElement(screen.getByTestId("data-eda-subset-bin-0"));
    expect(details).toContainElement(screen.getByTestId("data-eda-subset-coverage"));
  });

  it("reports how many records carry a value", () => {
    render(<DataEdaSubsetPreview data={EDA_SUBSET_PREVIEW_FIXTURE} />);
    expect(screen.getByTestId("data-eda-subset-coverage")).toHaveTextContent(
      "6 of 6 records have a value",
    );
  });

  it("keeps the coverage line out of the disclosure when values are missing", () => {
    render(
      <DataEdaSubsetPreview
        data={{
          ...EDA_SUBSET_PREVIEW_FIXTURE,
          distribution: { ...DISTRIBUTION, numVarValues: 4, numMissingCases: 2 },
        }}
      />,
    );
    const coverage = screen.getByTestId("data-eda-subset-coverage");
    expect(coverage.textContent).toBe("4 of 6 records have a value, 2 missing");
    expect(coverage.closest("details")).toBe(null);
    expect(screen.getByText("Bin counts").closest("details")).toContainElement(
      screen.getByTestId("data-eda-subset-bin-0"),
    );
  });

  it("warns when the variable is multi-valued, because the bars do not add up", () => {
    render(
      <DataEdaSubsetPreview
        data={{
          ...EDA_SUBSET_PREVIEW_FIXTURE,
          distribution: { ...DISTRIBUTION, isMultiValued: true, numVarValues: 9 },
        }}
      />,
    );
    const note = screen.getByTestId("data-eda-subset-multivalued");
    expect(note).toHaveTextContent("one record can carry several values");
    expect(note.closest("details")).toBe(null);
    expect(screen.getByTestId("data-eda-subset-coverage")).toHaveTextContent(
      "9 of 6 records have a value",
    );
  });

  it("omits the warning when the variable is single-valued", () => {
    render(<DataEdaSubsetPreview data={EDA_SUBSET_PREVIEW_FIXTURE} />);
    expect(screen.queryByTestId("data-eda-subset-multivalued")).toBe(null);
  });

  it("omits the histogram when the part carries no distribution", () => {
    render(
      <DataEdaSubsetPreview
        data={{ ...EDA_SUBSET_PREVIEW_FIXTURE, distribution: null }}
      />,
    );
    expect(screen.queryByTestId("data-eda-subset-histogram")).toBe(null);
    expect(screen.getByTestId("data-eda-subset-preview")).toHaveTextContent(
      "6 of 12 Sample",
    );
  });

  it("prints the note the backend attached to the distribution", () => {
    render(
      <DataEdaSubsetPreview
        data={{
          ...EDA_SUBSET_PREVIEW_FIXTURE,
          distributionNote: "Temperature has 40 bins, the first 10 are shown",
        }}
      />,
    );
    expect(screen.getByTestId("data-eda-subset-note")).toHaveTextContent(
      "Temperature has 40 bins, the first 10 are shown",
    );
  });

  it("hydrates the store", async () => {
    render(<DataEdaSubsetPreview data={EDA_SUBSET_PREVIEW_FIXTURE} />);
    await waitFor(() => {
      expect(useEdaStore.getState().subsetPreview?.entityCounts[0]?.count).toBe(6);
    });
  });
});

describe("the histogram's plot area", () => {
  it("leaves real room for the bars above the 64px of axis furniture", () => {
    const source = readFileSync(join(__dirname, "DataEdaSubsetPreview.tsx"), "utf8");
    const match = /const HISTOGRAM_HEIGHT = (\d+);/.exec(source);
    expect(match).not.toBeNull();
    expect(Number(match?.[1])).toBeGreaterThanOrEqual(160);
  });
});
