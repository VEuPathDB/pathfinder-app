/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { SAMPLE_RUN, SAMPLE_RUN_ID } from "./__fixtures__/sampleRun";
import { ReportSummary } from "./ReportSummary";

const UNSUMMARIZED = {
  ...SAMPLE_RUN,
  headline: [],
  disputed: [],
  errorTypes: SAMPLE_RUN.errorTypes.map((type) => ({
    ...type,
    cause: null,
    reviewed: [],
  })),
};

describe("ReportSummary", () => {
  it("states one headline line per reviewed error type, with its cause", () => {
    render(<ReportSummary view={SAMPLE_RUN} />);
    expect(
      screen.getByRole("heading", { level: 2, name: "Headline findings" }),
    ).toBeInTheDocument();
    const items = screen.getAllByRole("listitem").map((item) => item.textContent);
    expect(items[0]).toBe(
      "Intact gene called a pseudogene: 1 finding in Plasmodium falciparum NF54, high certainty. " +
        "Sample review: rebuilt through the reference coding sequence, the strain's DNA encodes all 1,386 bases with no stop inside.",
    );
    expect(
      screen.getByRole("link", { name: "Intact gene called a pseudogene" }),
    ).toHaveAttribute(
      "href",
      `/audits/${SAMPLE_RUN_ID}/errors/intact_gene_called_pseudogene`,
    );
    const headline = screen.getByRole("link", { name: /PfNF54_100037200/ });
    expect(headline).toHaveTextContent("reviewed impact 0.8");
    expect(headline).toHaveAttribute("href", `/audits/${SAMPLE_RUN_ID}/findings/1`);
    expect(
      screen.getByText(
        "Two independent reviews agreed on 1 of 2 sampled findings (50%)",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/of 5 named findings|four of five/)).toBe(null);
  });

  it("states what the two reviews disagree on", () => {
    render(<ReportSummary view={SAMPLE_RUN} />);
    expect(screen.getByRole("link", { name: /PfDd2_140076300/ })).toHaveTextContent(
      "The two independent reviews disagree: the first finds no error, the second keeps the error",
    );
  });

  it("says why there is no summary yet", () => {
    render(
      <ReportSummary
        view={{
          ...UNSUMMARIZED,
          reviewState: {
            status: "reviewing",
            text: "Reviewing findings",
            done: 2,
            total: 5,
            message: "",
          },
        }}
      />,
    );
    expect(screen.getByText("No summary yet: Reviewing findings")).toBeInTheDocument();
    const items = screen.getAllByRole("listitem").map((item) => item.textContent);
    expect(items[0]).toBe(
      "Intact gene called a pseudogene: 1 finding in Plasmodium falciparum NF54, high certainty.",
    );
  });

  it("says a run was not reviewed and shows no review-derived figure without its agreement", () => {
    render(
      <ReportSummary view={{ ...UNSUMMARIZED, reviewState: null, agreement: null }} />,
    );
    expect(screen.getByText("This run has not been reviewed.")).toBeInTheDocument();
    expect(screen.queryByText(/independent reviews/)).toBe(null);
  });

  it("states nothing about a run with no error and no review", () => {
    const { container } = render(
      <ReportSummary
        view={{ ...UNSUMMARIZED, errorTypes: [], reviewState: null, agreement: null }}
      />,
    );
    expect(container).toHaveTextContent(
      "Headline findingsThis run has not been reviewed.",
    );
  });
});
