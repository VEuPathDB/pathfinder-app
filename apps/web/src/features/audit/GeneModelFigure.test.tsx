/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import {
  AGAP3685_RETAINED_MODELS,
  SEC_SPLIT_STOP_MODELS,
} from "./__fixtures__/derivedModels";
import {
  AFU8_MODELS,
  AGAP3685_MODELS,
  GT1_SELK_MODELS,
  PKAC_MODELS,
  RPT6_MODELS,
} from "./__fixtures__/recordedModels";
import {
  pseudogeneConfirmation,
  strainConfirmation,
} from "./__fixtures__/sampleConfirmations";
import { sampleDetail } from "./__fixtures__/sampleRun";
import { GeneModelFigure } from "./GeneModelFigure";
import { confirmationTracks } from "./proteinTracks";

function parts(container: HTMLElement, part: string): Element[] {
  return [...container.querySelectorAll(`[data-part="${part}"]`)];
}

function attributes(elements: Element[], name: string): (string | null)[] {
  return elements.map((element) => element.getAttribute(name));
}

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
    expect(parts(container, "cds")).toHaveLength(9);
    expect(parts(container, "exon")).toHaveLength(9);
    expect(parts(container, "intron")).toHaveLength(7);
    expect(parts(container, "changed")).toHaveLength(3);
    expect(container.querySelector('[data-part="changed"]')).toHaveAttribute(
      "x",
      "40.4",
    );
    expect(screen.getAllByRole("listitem")[1]?.textContent).toBe(
      "Proposed by RNA-seq evidence, + strand: 5 exons at 1,381,622 to 1,381,745, 1,381,887 to 1,382,044, 1,382,281 to 1,382,465, 1,382,631 to 1,382,790 and 1,383,064 to 1,383,462; coded bases 1,381,622 to 1,381,745, 1,381,887 to 1,382,044, 1,382,281 to 1,382,465, 1,382,631 to 1,382,790 and 1,383,064 to 1,383,462; coded only here: 1,381,887 to 1,382,044 and 1,382,281 to 1,382,305; RNA-seq reads join bases 1,381,746 to 1,381,886 (1,436 reads) and 1,382,045 to 1,382,280 (1,686 reads)",
    );
    expect(parts(container, "junction")).toHaveLength(2);
  });

  it("calls the removed intron what it is, never coded bases", () => {
    render(<GeneModelFigure models={PKAC_MODELS} proteinTracks={[]} />);
    expect(screen.getAllByRole("listitem")[0]?.textContent).toBe(
      "Annotated PcyM_0736700, PcyM_0736700-t36_1, + strand: 4 exons at 1,381,622 to 1,381,745, 1,382,306 to 1,382,465, 1,382,631 to 1,382,790 and 1,383,064 to 1,383,462; coded bases 1,381,622 to 1,381,745, 1,382,306 to 1,382,465, 1,382,631 to 1,382,790 and 1,383,064 to 1,383,462; intron the RNA-seq does not support: 1,381,746 to 1,382,305",
    );
    expect(screen.getByText("Where the two models differ")).toBeInTheDocument();
  });

  it("states exons apart from coded bases when part of an exon is not coded", () => {
    render(<GeneModelFigure models={AFU8_MODELS} proteinTracks={[]} />);
    const [annotated, proposed] = screen.getAllByRole("listitem");
    expect(annotated).toHaveTextContent(
      "coded only here: 201,039 to 201,399, 201,454 to 201,595, 201,653 to 201,925 and 201,976 to 202,061",
    );
    expect(proposed).toHaveTextContent(
      "- strand: 5 exons at 201,039 to 201,399, 201,454 to 201,595, 201,653 to 201,925, 201,976 to 202,208 and 202,267 to 202,401; coded bases 202,062 to 202,208 and 202,267 to 202,401",
    );
  });

  it("gives a row with no correction read its exon coordinates and no coded bases", () => {
    render(<GeneModelFigure models={AGAP3685_RETAINED_MODELS} proteinTracks={[]} />);
    const proposed = screen.getAllByRole("listitem")[1];
    expect(proposed).toHaveTextContent(
      "Intron kept as exon (the RNA-seq does not splice it), - strand: 4 exons at 41,950,997 to 41,952,902, 41,953,562 to 41,953,639, 41,953,733 to 41,953,990 and 41,954,090 to 41,954,101",
    );
    expect(proposed?.textContent).not.toContain("coded bases");
  });

  it("draws a merge and the last coded codon with their own marks", () => {
    const merge = render(<GeneModelFigure models={RPT6_MODELS} proteinTracks={[]} />);
    expect(parts(merge.container, "span")).toHaveLength(1);
    expect(screen.getAllByRole("img")).toHaveLength(2);
    expect(screen.getAllByRole("listitem")[0]?.textContent).toBe(
      "Merged model AK88_02763, + strand: one model over bases 202,826 to 207,689",
    );
    merge.unmount();
    const sec = render(<GeneModelFigure models={GT1_SELK_MODELS} proteinTracks={[]} />);
    expect(parts(sec.container, "stop")).toHaveLength(1);
    const line = screen.getByText(/last coded codon at bases 5,361,334 to 5,361,336/);
    expect(line).toHaveTextContent("Model TGGT1_316600, + strand: 3 exons");
    expect(line.textContent).not.toContain("selenocysteine");
    expect(screen.getAllByText("last codon")).toHaveLength(1);
    expect(screen.queryByText("stop")).toBe(null);
  });

  it("draws a merged model to the scale of its own span, dashed", () => {
    const { container } = render(
      <GeneModelFigure models={RPT6_MODELS} proteinTracks={[]} />,
    );
    expect(
      screen.getByRole("img", {
        name: /Gene models on KQ001672, bases 202,826 to 207,689/,
      }),
    ).toBeInTheDocument();
    const [span] = parts(container, "span");
    expect(span).toHaveAttribute("x", "0.0");
    expect(span).toHaveAttribute("width", "600.0");
    expect(span).toHaveAttribute("stroke-dasharray", "4 3");
  });

  it("places each gene's arrow at that gene's own end", () => {
    const { container } = render(
      <GeneModelFigure models={RPT6_MODELS} proteinTracks={[]} />,
    );
    expect(attributes(parts(container, "strand"), "points")).toEqual([
      "600.0,14 606.0,21 600.0,28",
      "600.0,14 606.0,21 600.0,28",
      "253.3,14 259.3,21 253.3,28",
    ]);
  });

  it("writes the last codon's word at the codon", () => {
    render(<GeneModelFigure models={GT1_SELK_MODELS} proteinTracks={[]} />);
    expect(screen.getByText("last codon")).toHaveAttribute("x", "599.0");
  });

  it("draws every span of a last codon split by an intron", () => {
    const { container } = render(
      <GeneModelFigure models={SEC_SPLIT_STOP_MODELS} proteinTracks={[]} />,
    );
    expect(parts(container, "stop")).toHaveLength(2);
    expect(
      screen.getByText(
        /last coded codon at bases 5,360,415 to 5,360,415 and 5,361,335 to 5,361,336/,
      ),
    ).toBeInTheDocument();
  });

  it("marks a kept intron and says which intron its evidence describes", () => {
    const { container } = render(
      <GeneModelFigure models={AGAP3685_MODELS} proteinTracks={[]} />,
    );
    expect(parts(container, "kept")).toHaveLength(1);
    expect(screen.getAllByRole("listitem")[1]).toHaveTextContent(
      "intron kept as exon at 41,952,076 to 41,952,160: median depth 53% of the exons', 99% of its bases covered (E-MTAB-2880:E_20h_F (unique reverse))",
    );
  });

  it("points the arrow right on a + gene and left on a - gene", () => {
    const plus = render(<GeneModelFigure models={PKAC_MODELS} proteinTracks={[]} />);
    expect(parts(plus.container, "strand")[0]).toHaveAttribute(
      "points",
      "600.0,14 606.0,21 600.0,28",
    );
    plus.unmount();
    const minus = render(<GeneModelFigure models={AFU8_MODELS} proteinTracks={[]} />);
    expect(parts(minus.container, "strand")[0]).toHaveAttribute(
      "points",
      "0.0,14 -6.0,21 0.0,28",
    );
  });

  it("draws an exon as an outline and only its coded part filled", () => {
    const { container } = render(
      <GeneModelFigure models={AFU8_MODELS} proteinTracks={[]} />,
    );
    expect(parts(container, "exon")).toHaveLength(10);
    expect(parts(container, "cds")).toHaveLength(7);
    expect(new Set(attributes(parts(container, "exon"), "fill"))).toEqual(
      new Set(["none"]),
    );
    expect(new Set(attributes(parts(container, "cds"), "fill"))).toEqual(
      new Set(["hsl(var(--chart-1))"]),
    );
  });

  it("draws an intron as a line across its own bases", () => {
    const { container } = render(
      <GeneModelFigure models={PKAC_MODELS} proteinTracks={[]} />,
    );
    const [first] = parts(container, "intron");
    expect(first).toHaveAttribute("x1", "40.4");
    expect(first).toHaveAttribute("x2", "222.9");
  });

  it("arcs a junction between its two ends, with its reads in the middle", () => {
    const { container } = render(
      <GeneModelFigure models={PKAC_MODELS} proteinTracks={[]} />,
    );
    const [first] = parts(container, "junction");
    expect(first?.querySelector("path")).toHaveAttribute(
      "d",
      "M 40.4 28 Q 63.4 44 86.4 28",
    );
    expect(first?.querySelector("text")).toHaveAttribute("x", "63.4");
    expect(first?.querySelector("text")).toHaveTextContent("1,436 reads");
  });

  it("says one read in the singular", () => {
    const proposed = AFU8_MODELS.proposed;
    if (proposed === null || proposed === undefined) {
      throw new Error("the recording proposes a model");
    }
    render(
      <GeneModelFigure
        models={{ ...AFU8_MODELS, proposed: { ...proposed, junctionReads: [1] } }}
        proteinTracks={[]}
      />,
    );
    expect(screen.getByText("1 read")).toBeInTheDocument();
    expect(screen.queryByText("1 reads")).toBe(null);
  });

  it("stacks the rows of a track one under the other and the scale under them", () => {
    const { container } = render(
      <GeneModelFigure models={PKAC_MODELS} proteinTracks={[]} />,
    );
    expect(
      attributes([...container.querySelectorAll("g[data-row]")], "transform"),
    ).toEqual(["translate(0 0)", "translate(0 36)"]);
    expect(parts(container, "scale")[0]).toHaveAttribute(
      "transform",
      "translate(0 86)",
    );
  });

  it("draws a base scale under each track and the protein tracks after the figure", () => {
    const { models } = sampleDetail("strain_model");
    if (models === null) throw new Error("the sample strain finding stores its models");
    const { container } = render(
      <GeneModelFigure
        models={models}
        proteinTracks={confirmationTracks(strainConfirmation())}
      />,
    );
    expect(parts(container, "scale")).toHaveLength(2);
    expect(
      [...(parts(container, "scale")[0]?.querySelectorAll("text") ?? [])].map(
        (label) => label.textContent,
      ),
    ).toEqual(["1,381,622", "1,841 bases", "1,383,462"]);
    expect(
      screen.getByRole("img", { name: /Protein lengths of the two models/ }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("img")).toHaveLength(3);
    expect(container.querySelector("figure figure")).toBe(null);
  });

  it("titles a pseudogene's tracks as coding sequences, not protein lengths", () => {
    render(
      <GeneModelFigure
        models={{ kind: "pseudogene", annotated: PKAC_MODELS.annotated }}
        proteinTracks={confirmationTracks(pseudogeneConfirmation())}
      />,
    );
    expect(
      screen.getByRole("img", { name: /Coding sequences of the two genes, in codons/ }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /Protein lengths/ })).toBe(null);
  });

  it("draws a coded part with no exon and no strand arrow for it", () => {
    const [first] = PKAC_MODELS.annotated;
    if (first === undefined) throw new Error("the PKAC models hold a model");
    const { container } = render(
      <GeneModelFigure
        models={{ kind: "length", annotated: [{ ...first, exons: [] }] }}
        proteinTracks={[]}
      />,
    );
    expect(parts(container, "cds")).toHaveLength(first.cds.length);
    expect(parts(container, "strand")).toHaveLength(0);
  });
});
