/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";

import { ChatHelpersProvider } from "../../runtime/chatHelpersContext";
import type { VariantComparison } from "@pathfinder/shared";

import { DataVariantComparison } from "./DataVariantComparison";
import { chatHelpersFor, threadOf, threadPart } from "./threadFixture";

const COMPARISON: VariantComparison = {
  variants: [
    {
      label: "kinases",
      searchName: "GenesByText",
      geneCount: 1105,
      uniqueCount: 84,
      sampleUniqueGenes: ["PF3D7_0100100"],
    },
    {
      label: "phosphatases",
      searchName: "GenesByText",
      geneCount: 342,
      uniqueCount: 12,
      sampleUniqueGenes: [],
    },
  ],
  overlaps: [{ a: "kinases", b: "phosphatases", shared: 30, jaccard: 0.02 }],
  truncated: false,
};

function inThread(ui: ReactElement<{ data: object }>) {
  const messages = threadOf([threadPart("data-variant-comparison", ui.props.data)]);
  return render(
    <ChatHelpersProvider value={chatHelpersFor(messages)}>{ui}</ChatHelpersProvider>,
  );
}

describe("DataVariantComparison", () => {
  it("captions the figure with the variant count and the largest set", () => {
    inThread(<DataVariantComparison data={COMPARISON} />);
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "Table 1. 2 variants, 1,105 genes in the largest",
    );
  });

  it("titles the figure Variants and keeps every label in the body", () => {
    inThread(<DataVariantComparison data={COMPARISON} />);
    const title = screen.getByText("Variants");
    expect(title.parentElement?.tagName).toBe("FIGCAPTION");
    const card = screen.getByTestId("data-variant-comparison");
    expect(card).toHaveTextContent("kinases");
    expect(card).toHaveTextContent("phosphatases");
  });

  it("reads zero in the largest when every variant failed", () => {
    inThread(
      <DataVariantComparison
        data={{
          variants: [
            {
              label: "kinases",
              searchName: "GenesByText",
              geneCount: 0,
              uniqueCount: 0,
              sampleUniqueGenes: [],
              error: "search timed out",
            },
          ],
          overlaps: [],
        }}
      />,
    );
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "Table 1. 1 variants, 0 genes in the largest",
    );
    expect(screen.getByTestId("data-variant-comparison")).toHaveTextContent(
      "failed: search timed out",
    );
  });

  it("tabulates each variant's genes and the genes only it returned", () => {
    inThread(<DataVariantComparison data={COMPARISON} />);

    const heads = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(heads).toEqual(["Variant", "Genes", "Unique to it"]);
    const rows = screen.getAllByRole("row").map((r) => r.textContent);
    expect(rows[1]).toBe("kinases1,10584");
    expect(rows[2]).toBe("phosphatases34212");
    expect(screen.getByText("Only in kinases:")).toBeInTheDocument();
    expect(screen.getByText("PF3D7_0100100")).toBeInTheDocument();
    expect(screen.getByText("kinases vs phosphatases:")).toBeInTheDocument();
  });

  it("draws no divider, no card and no outer margin", () => {
    inThread(<DataVariantComparison data={COMPARISON} />);
    expect(screen.getByTestId("figure").className).toBe("");
    expect(screen.getByTestId("data-variant-comparison").className).not.toMatch(
      /\bborder\b|\brounded-md\b|\bbg-card\b/,
    );
  });
});
