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
      sampleUniqueGenes: [
        { geneId: "PF3D7_0100100", product: "erythrocyte membrane protein 1, PfEMP1" },
      ],
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
  it("shows the result count of each variant where the strategy was counted", () => {
    const counted: VariantComparison = {
      variants: [
        {
          label: "Minimum 2",
          searchName: "GenesByTransmembraneDomains",
          geneCount: 1490,
          uniqueCount: 461,
          sampleUniqueGenes: [],
          resultCount: 227,
        },
        {
          label: "Minimum 3",
          searchName: "GenesByTransmembraneDomains",
          geneCount: 1029,
          uniqueCount: 0,
          sampleUniqueGenes: [],
          resultCount: 82,
        },
      ],
      overlaps: [{ a: "Minimum 2", b: "Minimum 3", shared: 1029, jaccard: 0.6906 }],
      resultStepId: "step_intersect",
    };
    inThread(<DataVariantComparison data={counted} />);
    const card = screen.getByTestId("data-variant-comparison");
    expect(Array.from(card.querySelectorAll("th")).map((th) => th.textContent)).toEqual(
      ["Variant", "Genes", "Unique to it", "In the result"],
    );
    expect(
      Array.from(card.querySelectorAll("tbody tr")).map((tr) =>
        Array.from(tr.querySelectorAll("td")).map((td) => td.textContent),
      ),
    ).toEqual([
      ["Minimum 2", "1,490", "461", "227"],
      ["Minimum 3", "1,029", "0", "82"],
    ]);
  });

  it("adds no result column where no variant was counted in the strategy", () => {
    inThread(<DataVariantComparison data={COMPARISON} />);
    const card = screen.getByTestId("data-variant-comparison");
    expect(Array.from(card.querySelectorAll("th")).map((th) => th.textContent)).toEqual(
      ["Variant", "Genes", "Unique to it"],
    );
  });

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

  it("names each gene only one variant returned with its product", () => {
    inThread(
      <DataVariantComparison
        data={{
          variants: [
            {
              label: "word",
              searchName: "GenesByText",
              geneCount: 12,
              uniqueCount: 11,
              sampleUniqueGenes: [
                {
                  geneId: "TcIL3000_0_29570",
                  product: "Glucose-6-phosphate isomerase (GPI) (EC 5.3.1.9)",
                },
                { geneId: "TcIL3000_10_11240", product: "gpi mannosyltransferase 2" },
                { geneId: "TcIL3000_10_4250", product: null },
              ],
            },
            {
              label: "phrase",
              searchName: "GenesByText",
              geneCount: 1,
              uniqueCount: 0,
              sampleUniqueGenes: [],
            },
          ],
          overlaps: [],
        }}
      />,
    );
    expect(
      screen.getAllByTestId("variant-unique-gene").map((gene) => gene.textContent),
    ).toEqual([
      "TcIL3000_0_29570 Glucose-6-phosphate isomerase (GPI) (EC 5.3.1.9)",
      "TcIL3000_10_11240 gpi mannosyltransferase 2",
      "TcIL3000_10_4250",
    ]);
  });

  it("lists under each label the parameter values it differs by", () => {
    inThread(
      <DataVariantComparison
        data={{
          variants: [
            {
              label: "Product only",
              searchName: "GenesByText",
              geneCount: 1,
              uniqueCount: 0,
              sampleUniqueGenes: [],
            },
            {
              label: "Every text field",
              searchName: "GenesByText",
              geneCount: 2,
              uniqueCount: 1,
              sampleUniqueGenes: [],
              differsBy: { text_fields: '["product", "name", "so_id"]', min_tm: "2" },
            },
          ],
          overlaps: [],
        }}
      />,
    );
    const lines = screen
      .getAllByTestId("variant-differs-by")
      .map((line) => line.textContent);
    expect(lines).toEqual(["text_fields: product, name, so_id", "min_tm: 2"]);
    const rows = screen.getAllByRole("row");
    expect(rows[1]).not.toHaveTextContent("text_fields");
    expect(rows[2]).toHaveTextContent("text_fields: product, name, so_id");
  });

  it("shows no parameter line where differsBy is empty", () => {
    inThread(
      <DataVariantComparison
        data={{
          ...COMPARISON,
          variants: COMPARISON.variants.map((variant) => ({
            ...variant,
            differsBy: {},
          })),
        }}
      />,
    );
    expect(screen.queryAllByTestId("variant-differs-by")).toHaveLength(0);
  });

  it("draws no divider, no card and no outer margin", () => {
    inThread(<DataVariantComparison data={COMPARISON} />);
    expect(screen.getByTestId("figure").className).toBe("");
    expect(screen.getByTestId("data-variant-comparison").className).not.toMatch(
      /\bborder\b|\brounded-md\b|\bbg-card\b/,
    );
  });
});
