/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { SAMPLE_RUN, SAMPLE_WORDS } from "./__fixtures__/sampleRun";
import { gapText } from "./format";
import { RateTable } from "./RateTable";

const [FIRST_GENOME] = SAMPLE_RUN.genomes;
if (FIRST_GENOME === undefined) throw new Error("the sample run holds genomes");

describe("RateTable", () => {
  it("puts beside each rate its share, its range, the unjudged and the unresolved by status", () => {
    render(<RateTable view={SAMPLE_RUN} words={SAMPLE_WORDS} />);
    expect(
      screen.getByRole("table", {
        name: "Error rate in the random sample, by screened genome and check",
      }),
    ).toBeInTheDocument();
    const dd2 = within(screen.getByRole("row", { name: /Plasmodium falciparum Dd2/ }));
    expect(dd2.getByText("1 of 3")).toBeInTheDocument();
    expect(dd2.getByText("33% (6% to 79%)")).toBeInTheDocument();
    expect(dd2.getByText("17% to 67%")).toBeInTheDocument();
    expect(
      dd2.getByText(
        "3 (1 not in the random sample, 1 where the site did not answer, 1 not read before the run's deadline)",
      ),
    ).toBeInTheDocument();
    expect(dd2.getByText("Not served by the site")).toBeInTheDocument();
    const nf54 = within(
      screen.getByRole("row", { name: /Plasmodium falciparum NF54/ }),
    );
    expect(nf54.getByText("100% (21% to 100%)")).toBeInTheDocument();
  });

  it("says a check judged nothing in place of a rate", () => {
    const rates = SAMPLE_RUN.rates.map((rate) => ({ ...rate, bounds: null }));
    render(<RateTable view={{ ...SAMPLE_RUN, rates }} words={SAMPLE_WORDS} />);
    expect(screen.getAllByText("No judged finding")).toHaveLength(2);
  });

  it("says an error traced to another genome's model counts clean here", () => {
    render(<RateTable view={SAMPLE_RUN} words={SAMPLE_WORDS} />);
    expect(
      screen.getByText(
        "An error the check traced to another genome's model counts as correct here, and the findings list it under that genome.",
      ),
    ).toBeInTheDocument();
  });

  it("reads a BUSCO gap the site served, one it did not serve, and one whose read failed", () => {
    const nf135 = {
      ...FIRST_GENOME,
      priority: {
        organism: "Plasmodium falciparum NF135.C10",
        protein: { complete: 93.0, fragmented: 0.1, missing: 6.9, total: 1378 },
        genome: { complete: 98.4, fragmented: 0.3, missing: 1.3, total: 1378 },
        lineage: "aconoidasida_odb12",
        gap: 5.4,
      },
    };
    expect(gapText(nf135)).toBe("5.4 points");
    expect(gapText({ ...nf135, priority: null, message: null })).toBe(
      "Not served by the site",
    );
    expect(
      gapText({
        ...nf135,
        priority: null,
        message: "the BUSCO report of plasmodb is unreadable",
      }),
    ).toBe("Unknown: the scores read failed");
  });
});
