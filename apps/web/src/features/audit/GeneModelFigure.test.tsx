/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import {
  AFU8_MODELS,
  AGAP3685_MODELS,
  AGAP3685_RETAINED_MODELS,
  GT1_SELK_MODELS,
  PKAC_MODELS,
  RPT6_MODELS,
} from "./__fixtures__/recordedModels";
import { strainConfirmation } from "./__fixtures__/sampleConfirmations";
import { sampleDetail } from "./__fixtures__/sampleRun";
import { GeneModelFigure } from "./GeneModelFigure";
import { confirmationTracks } from "./proteinTracks";

describe("GeneModelFigure", () => {
  it("draws the annotated and the proposed model, states them in words and marks what changed", () => {
    const { container } = render(
      <GeneModelFigure models={PKAC_MODELS} proteinTracks={[]} />,
    );
    expect(
      screen.getByRole("img", {
        name: /Gene models on PcyM_07, bases 1,381,622 to 1,383,462/,
      }),
    ).toBeInTheDocument();
    expect(container.querySelectorAll('[data-part="cds"]')).toHaveLength(9);
    expect(container.querySelectorAll('[data-part="exon"]')).toHaveLength(9);
    expect(container.querySelectorAll('[data-part="intron"]')).toHaveLength(7);
    expect(container.querySelectorAll('[data-part="changed"]')).toHaveLength(3);
    expect(container.querySelector('[data-part="changed"]')).toHaveAttribute(
      "x",
      "40.4",
    );
    const items = screen.getAllByRole("listitem");
    expect(items[1]).toHaveTextContent(
      "Proposed by RNA-seq evidence, + strand: 5 coded parts; coded only here: 1,381,887 to 1,382,044 and 1,382,281 to 1,382,305",
    );
    expect(items[1]).toHaveTextContent(
      "RNA-seq reads join bases 1,381,746 to 1,381,886 (1,436 reads) and 1,382,045 to 1,382,280 (1,686 reads)",
    );
    expect(container.querySelectorAll('[data-part="junction"]')).toHaveLength(2);
  });

  it("calls the removed intron what it is, never coded bases", () => {
    render(<GeneModelFigure models={PKAC_MODELS} proteinTracks={[]} />);
    const annotated = screen.getAllByRole("listitem")[0];
    expect(annotated?.textContent).toBe(
      "Annotated PcyM_0736700, PcyM_0736700-t36_1, + strand: 4 exons; coded bases 1,381,622 to 1,381,745, 1,382,306 to 1,382,465, 1,382,631 to 1,382,790 and 1,383,064 to 1,383,462; intron the RNA-seq does not support: 1,381,746 to 1,382,305",
    );
    expect(screen.getByText("Where the two models differ")).toBeInTheDocument();
  });

  it("states the bases an annotated model codes alone when the proposal drops them", () => {
    render(<GeneModelFigure models={AFU8_MODELS} proteinTracks={[]} />);
    expect(screen.getAllByRole("listitem")[0]).toHaveTextContent(
      "coded only here: 201,039 to 201,399, 201,454 to 201,595, 201,653 to 201,925 and 201,976 to 202,061",
    );
  });

  it("draws a merge and a selenoprotein end with their own marks", () => {
    const merge = render(<GeneModelFigure models={RPT6_MODELS} proteinTracks={[]} />);
    expect(merge.container.querySelectorAll('[data-part="span"]')).toHaveLength(1);
    expect(screen.getAllByRole("img")).toHaveLength(2);
    expect(screen.getAllByRole("listitem")[0]?.textContent).toBe(
      "Merged model AK88_02763, + strand: one model over bases 202,826 to 207,689",
    );
    merge.unmount();
    const sec = render(<GeneModelFigure models={GT1_SELK_MODELS} proteinTracks={[]} />);
    expect(sec.container.querySelectorAll('[data-part="stop"]')).toHaveLength(1);
    expect(
      screen.getByText(/stop codon at bases 5,361,334 to 5,361,336/),
    ).toHaveTextContent(
      "TGGT1_316600, stops at its selenocysteine codon, + strand: 3 exons",
    );
    expect(screen.getAllByText("stop")).toHaveLength(1);
  });

  it("marks a kept intron and states the evidence for keeping it", () => {
    const { container } = render(
      <GeneModelFigure models={AGAP3685_MODELS} proteinTracks={[]} />,
    );
    expect(container.querySelectorAll('[data-part="kept"]')).toHaveLength(1);
    expect(screen.getAllByRole("listitem")[1]).toHaveTextContent(
      "intron kept as exon: 41,952,076 to 41,952,160; median depth 53% of the exons', 99% of its bases covered (E-MTAB-2880:E_20h_F (unique reverse))",
    );
  });

  it("counts exons, not coded parts, for an intron kept with no correction read", () => {
    render(<GeneModelFigure models={AGAP3685_RETAINED_MODELS} proteinTracks={[]} />);
    expect(screen.getAllByRole("listitem")[1]).toHaveTextContent(
      "Intron kept as exon (the RNA-seq does not splice it), - strand: 4 exons",
    );
  });

  it("points the strand arrow to the row's end", () => {
    const plus = render(<GeneModelFigure models={PKAC_MODELS} proteinTracks={[]} />);
    expect(plus.container.querySelector('[data-part="strand"]')).toHaveAttribute(
      "data-strand",
      "+",
    );
    plus.unmount();
    const minus = render(<GeneModelFigure models={AFU8_MODELS} proteinTracks={[]} />);
    expect(minus.container.querySelector('[data-part="strand"]')).toHaveAttribute(
      "data-strand",
      "-",
    );
  });

  it("draws a base scale under each track and the protein tracks underneath", () => {
    const { models } = sampleDetail("strain_model");
    if (models === null) throw new Error("the sample strain finding stores its models");
    const { container } = render(
      <GeneModelFigure
        models={models}
        proteinTracks={confirmationTracks(strainConfirmation())}
      />,
    );
    expect(container.querySelectorAll('[data-part="scale"]')).toHaveLength(2);
    expect(screen.getByText("1,841 bases")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /Protein lengths of the two models/ }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("img")).toHaveLength(3);
  });
});
