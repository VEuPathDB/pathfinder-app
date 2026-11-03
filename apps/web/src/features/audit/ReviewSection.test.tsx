/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { FindingDetail } from "@pathfinder/shared/generated/types/FindingDetail";

import {
  SAMPLE_DETAILS,
  SAMPLE_RUN,
  SAMPLE_WORDS,
  sampleDetail,
} from "./__fixtures__/sampleRun";
import { ReviewSection } from "./ReviewSection";

function show(detail: FindingDetail) {
  render(
    <ReviewSection
      detail={detail}
      agreement={SAMPLE_RUN.agreement}
      reviewState={SAMPLE_RUN.reviewState}
      words={SAMPLE_WORDS}
    />,
  );
}

describe("ReviewSection", () => {
  it("states the review of a kept finding, its fix and its changed impact", () => {
    show(sampleDetail("pseudogene_call"));
    expect(screen.getByRole("region", { name: "Review" })).toBeInTheDocument();
    expect(screen.getByText("The review keeps the error")).toBeInTheDocument();
    expect(screen.getByText("The literature was not searched")).toBeInTheDocument();
    expect(screen.getByText("Suggested fix").nextElementSibling).toHaveTextContent(
      "Sample fix: annotate PfNF54_100037200 as protein coding, with the coding sequence its reference PF3D7_1032400 gives.",
    );
    expect(
      screen.getByText("A second, independent review: The review keeps the error"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Two independent reviews agreed on 1 of 2 sampled findings (50%)",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Impact after review 0.8 \(screen impact 0.5\)/),
    ).toHaveTextContent("the reference gene's record cites two PubMed articles");
    expect(
      screen.getByText(
        "Not checked whether a published study depends on this gene's model",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Error named").nextElementSibling).toHaveTextContent(
      "Intact gene called a pseudogene, high certainty",
    );
  });

  it("links a source with an address and keeps any other source as text", () => {
    const detail = sampleDetail("pseudogene_call");
    const review = detail.review;
    if (review === null) throw new Error("the sample finding holds a review");
    show({
      ...detail,
      review: {
        ...review,
        alreadyKnown: "known",
        knownFrom: ["https://example.org/paper", "PMID:123", "javascript:alert(1)"],
      },
    });
    const link = screen.getByRole("link", { name: "https://example.org/paper" });
    expect(link).toHaveAttribute("href", "https://example.org/paper");
    expect(link).toHaveAttribute("rel", "noreferrer");
    expect(screen.getByText("PMID:123").closest("a")).toBe(null);
    expect(screen.getByText("javascript:alert(1)").closest("a")).toBe(null);
  });

  it("says a finding is not reviewed, with the run's review state", () => {
    const detail = SAMPLE_DETAILS[2];
    if (detail === undefined) throw new Error("the sample run holds details");
    show(detail);
    expect(screen.getByText("Not reviewed yet.")).toBeInTheDocument();
    expect(screen.getByText("Reviewed and summarized")).toBeInTheDocument();
  });
});
