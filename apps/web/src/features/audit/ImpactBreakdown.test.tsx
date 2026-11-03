/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { SAMPLE_DETAILS, sampleDetail } from "./__fixtures__/sampleRun";
import { ImpactBreakdown } from "./ImpactBreakdown";
import { genomeUseText } from "./impactWords";

describe("ImpactBreakdown", () => {
  it("states the three factors of a cited finding", () => {
    render(<ImpactBreakdown finding={sampleDetail("pseudogene_call").finding} />);
    expect(
      screen.getByRole("heading", { level: 2, name: "Impact 0.5" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "Certainty: 1 (high certainty)",
      "Gene importance: 1, because a gene record cites a paper or holds a comment (PF3D7_1032400)",
      "Genome use: 0.5, because the site does not mark this genome as its species' reference strain (Plasmodium falciparum NF54)",
    ]);
    expect(screen.queryByText(/lower value/)).toBe(null);
  });

  it("marks an input that was not read and the lower value used for it", () => {
    render(<ImpactBreakdown finding={sampleDetail("strain_model").finding} />);
    expect(
      screen.getByRole("heading", { level: 2, name: "Impact 0.25" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("1 input was not read, so its lower value is used."),
    ).toBeInTheDocument();
    expect(screen.getByText("Fallback")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")[2]).toHaveTextContent(
      "Genome use: 0.5, because the strain model of its strain pair (Plasmodium cynomolgi strain M)",
    );
  });

  it("counts two inputs that were not read", () => {
    const { finding } = sampleDetail("strain_model");
    const { weighing } = finding;
    if (weighing === null) throw new Error("the sample strain finding is weighed");
    render(
      <ImpactBreakdown
        finding={{
          ...finding,
          weighing: {
            ...weighing,
            use: { ...weighing.use, source: "unknown" },
          },
        }}
      />,
    );
    expect(
      screen.getByText("2 inputs were not read, so their lower values are used."),
    ).toBeInTheDocument();
  });

  it("says a finding with no error has no impact", () => {
    const clean = SAMPLE_DETAILS[2];
    if (clean === undefined) throw new Error("the sample holds a clean finding");
    render(<ImpactBreakdown finding={clean.finding} />);
    expect(
      screen.getByText(
        "Not weighed: only a finding that names an error has an impact.",
      ),
    ).toBeInTheDocument();
  });
});

describe("genomeUseText", () => {
  it("reads a model's place in its strain pair", () => {
    const use = {
      genome: "Plasmodium cynomolgi strain B",
      source: "model_role",
      value: 1,
    } as const;
    expect(genomeUseText({ ...use, reference: true })).toBe(
      "the reference model of its strain pair",
    );
    expect(genomeUseText({ ...use, reference: false })).toBe(
      "the strain model of its strain pair",
    );
  });
});
