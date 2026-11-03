import { describe, expect, it } from "vitest";

import {
  AGAP3685_NONCANONICAL_MODELS,
  AGAP3685_RETAINED_MODELS,
  GT1_SELK_NOT_AT_SEC_MODELS,
  SEC_MINUS_STRAND_MODELS,
  SEC_SPLIT_STOP_MODELS,
} from "./__fixtures__/derivedModels";
import {
  AFU8_MODELS,
  AGAP3685_MODELS,
  AGAP7279_MODELS,
  GT1_SELK_MODELS,
  PKAC_MODELS,
  RPT6_MODELS,
} from "./__fixtures__/recordedModels";
import { sampleDetail } from "./__fixtures__/sampleRun";
import { changedSpans, geneModelTracks, placeBox } from "./geneModelTracks";

describe("geneModelTracks", () => {
  it("lays the PKAC model over the one the RNA-seq junctions propose", () => {
    const [track] = geneModelTracks(PKAC_MODELS);
    expect([track?.seqid, track?.window]).toEqual(["PcyM_07", [1381622, 1383462]]);
    const [annotated, proposed] = track?.rows ?? [];
    expect(annotated?.label).toBe("Annotated PcyM_0736700, PcyM_0736700-t36_1");
    expect(annotated?.cds).toEqual([
      { start: 1381622, end: 1381745 },
      { start: 1382306, end: 1382465 },
      { start: 1382631, end: 1382790 },
      { start: 1383064, end: 1383462 },
    ]);
    expect(annotated?.changed).toEqual([{ start: 1381746, end: 1382305 }]);
    expect(proposed?.changed).toEqual([
      { start: 1381887, end: 1382044 },
      { start: 1382281, end: 1382305 },
    ]);
    expect(proposed?.introns).toEqual([
      { start: 1381746, end: 1381886 },
      { start: 1382045, end: 1382280 },
      { start: 1382466, end: 1382630 },
      { start: 1382791, end: 1383063 },
    ]);
    expect(proposed?.junctions).toEqual([
      { box: { start: 1381746, end: 1381886 }, reads: 1436 },
      { box: { start: 1382045, end: 1382280 }, reads: 1686 },
    ]);
  });

  it("keeps apart the intron a proposal removes and the bases one model codes alone", () => {
    const [annotated, proposed] = geneModelTracks(PKAC_MODELS)[0]?.rows ?? [];
    expect([annotated?.codedOnly, annotated?.unsupported]).toEqual([
      [],
      [{ start: 1381746, end: 1382305 }],
    ]);
    expect([proposed?.codedOnly, proposed?.unsupported]).toEqual([
      [
        { start: 1381887, end: 1382044 },
        { start: 1382281, end: 1382305 },
      ],
      [],
    ]);
  });

  it("draws a proposal's exons outside its coding sequence when the frame moves", () => {
    const [annotated, proposed] = geneModelTracks(AFU8_MODELS)[0]?.rows ?? [];
    expect(proposed?.exons).toHaveLength(5);
    expect(proposed?.cds).toEqual([
      { start: 202062, end: 202208 },
      { start: 202267, end: 202401 },
    ]);
    expect(annotated?.codedOnly).toEqual([
      { start: 201039, end: 201399 },
      { start: 201454, end: 201595 },
      { start: 201653, end: 201925 },
      { start: 201976, end: 202061 },
    ]);
    expect(annotated?.unsupported).toEqual([{ start: 202070, end: 202266 }]);
  });

  it("draws a strain model beside its reference, each on its own sequence", () => {
    const { models } = sampleDetail("strain_model");
    if (models === null) throw new Error("the sample strain finding stores its models");
    expect(
      geneModelTracks(models).map((track) => [
        track.seqid,
        track.rows.map((row) => row.label),
      ]),
    ).toEqual([
      ["PcyM_07", ["Strain model PcyM_0736700"]],
      ["DF157099", ["Reference model PCYB_074210"]],
    ]);
  });

  it("names a lone model of a pair by neither role, for its partner was not read", () => {
    const { models } = sampleDetail("strain_model");
    if (models === null) throw new Error("the sample strain finding stores its models");
    expect(
      geneModelTracks({
        ...models,
        annotated: models.annotated.slice(1),
      }).map((track) => track.rows.map((row) => row.label)),
    ).toEqual([["Model PCYB_074210"]]);
  });

  it("draws a merge as the merged span beside the two genes it joins", () => {
    const [merged, genes] = geneModelTracks(RPT6_MODELS);
    expect(merged?.seqid).toBe("KQ001672");
    expect(merged?.rows.map((row) => [row.label, row.span, row.exons.length])).toEqual([
      ["Merged model AK88_02763", { start: 202826, end: 207689 }, 0],
    ]);
    expect(genes?.seqid).toBe("CP016252");
    expect(genes?.window).toEqual([248191, 252788]);
    expect(genes?.rows.map((row) => row.label)).toEqual([
      "Reference PCOAH_00051830",
      "Partner PCOAH_00051820",
    ]);
  });

  it("marks the model's last coded codon and claims nothing about selenocysteine", () => {
    for (const models of [GT1_SELK_MODELS, GT1_SELK_NOT_AT_SEC_MODELS]) {
      const [gene, reference] = geneModelTracks(models);
      expect(gene?.rows.map((row) => [row.label, row.stop])).toEqual([
        ["Model TGGT1_316600", [{ start: 5361334, end: 5361336 }]],
      ]);
      expect(reference?.rows.map((row) => [row.label, row.stop])).toEqual([
        ["Reference TGME49_316600", []],
      ]);
    }
  });

  it("finds the last coded codon at the low end of a minus-strand model", () => {
    const [gene] = geneModelTracks(SEC_MINUS_STRAND_MODELS);
    expect(gene?.rows[0]?.stop).toEqual([{ start: 5359580, end: 5359582 }]);
  });

  it("keeps every span of a last codon split by an intron", () => {
    const [gene] = geneModelTracks(SEC_SPLIT_STOP_MODELS);
    expect(gene?.rows[0]?.stop).toEqual([
      { start: 5360415, end: 5360415 },
      { start: 5361335, end: 5361336 },
    ]);
  });

  it("draws a replacing junction with its reads", () => {
    const [replaced] = geneModelTracks(AFU8_MODELS);
    expect(replaced?.rows[1]?.junctions).toEqual([
      { box: { start: 202209, end: 202266 }, reads: 18608 },
    ]);
  });

  it("says reads are unknown when the junctions and their reads do not pair", () => {
    const proposed = AFU8_MODELS.proposed;
    if (proposed === null || proposed === undefined) {
      throw new Error("the recording proposes a model");
    }
    const [track] = geneModelTracks({
      ...AFU8_MODELS,
      proposed: { ...proposed, junctionReads: [] },
    });
    expect(track?.rows[1]?.junctions).toEqual([
      { box: { start: 202209, end: 202266 }, reads: null },
    ]);
  });

  it("says which intron each note describes when two are kept", () => {
    const proposed = AGAP3685_MODELS.proposed;
    const kept = AGAP3685_NONCANONICAL_MODELS.proposed?.kept?.[0];
    if (proposed === null || proposed === undefined || kept === undefined) {
      throw new Error("the fixtures keep an intron");
    }
    const [track] = geneModelTracks({
      ...AGAP3685_MODELS,
      proposed: {
        ...proposed,
        kept: [...(proposed.kept ?? []), { ...kept, start: 41952903, end: 41953561 }],
      },
    });
    expect(track?.rows[1]?.notes).toEqual([
      "intron kept as exon at 41,952,076 to 41,952,160: median depth 53% of the exons', 99% of its bases covered (E-MTAB-2880:E_20h_F (unique reverse))",
      "intron kept as exon at 41,952,903 to 41,953,561: splice-site bases AT..AC",
    ]);
  });

  it("marks a retained intron inside the proposed exon with its depth", () => {
    const [annotated, proposed] = geneModelTracks(AGAP3685_MODELS)[0]?.rows ?? [];
    expect(proposed?.label).toBe("Proposed by RNA-seq evidence");
    expect(proposed?.cds).toHaveLength(4);
    expect(proposed?.kept).toEqual([{ start: 41952076, end: 41952160 }]);
    expect(proposed?.notes).toEqual([
      "intron kept as exon at 41,952,076 to 41,952,160: median depth 53% of the exons', 99% of its bases covered (E-MTAB-2880:E_20h_F (unique reverse))",
    ]);
    expect(annotated?.unsupported).toEqual([{ start: 41952076, end: 41952160 }]);
    expect(annotated?.codedOnly).toEqual([{ start: 41951666, end: 41952050 }]);
  });

  it("names a noncanonical intron by its splice-site bases", () => {
    const proposed = geneModelTracks(AGAP3685_NONCANONICAL_MODELS)[0]?.rows[1];
    expect(proposed?.notes).toEqual([
      "intron kept as exon at 41,952,076 to 41,952,160: splice-site bases AT..AC",
    ]);
  });

  it("keeps a retained intron as exon with no coding sequence when no correction was read", () => {
    const [annotated, proposed] =
      geneModelTracks(AGAP3685_RETAINED_MODELS)[0]?.rows ?? [];
    expect(proposed?.label).toBe(
      "Intron kept as exon (the RNA-seq does not splice it)",
    );
    expect(proposed?.cds).toEqual([]);
    expect(proposed?.changed).toEqual([{ start: 41952076, end: 41952160 }]);
    expect(proposed?.codedOnly).toEqual([]);
    expect(annotated?.codedOnly).toEqual([]);
    expect(annotated?.changed).toEqual([{ start: 41952076, end: 41952160 }]);
  });

  it("draws the annotated model alone when the check proposes none", () => {
    const [track] = geneModelTracks(AGAP7279_MODELS);
    expect(track?.rows.map((row) => row.label)).toEqual([
      "Annotated AGAP007279, AGAP007279-RA",
    ]);
    expect(track?.rows[0]?.changed).toEqual([]);
  });

  it("names a length finding's models and a pseudogene call's reference", () => {
    const annotated = PKAC_MODELS.annotated;
    expect(
      geneModelTracks({ kind: "length", annotated })[0]?.rows.map((row) => row.label),
    ).toEqual(["Annotated PcyM_0736700"]);
    expect(
      geneModelTracks({ kind: "pseudogene", annotated })[0]?.rows.map(
        (row) => row.label,
      ),
    ).toEqual(["Reference PcyM_0736700"]);
  });
});

describe("changedSpans", () => {
  it("states the bases each list holds and the other does not", () => {
    expect(
      changedSpans(
        [
          { start: 10, end: 20 },
          { start: 30, end: 40 },
        ],
        [{ start: 15, end: 35 }],
      ),
    ).toEqual({
      annotated: [
        { start: 10, end: 14 },
        { start: 36, end: 40 },
      ],
      proposed: [{ start: 21, end: 29 }],
    });
  });
});

describe("placeBox", () => {
  it("places a box on the window to the base", () => {
    const exon = placeBox({ start: 1381887, end: 1382044 }, [1381622, 1383462], 600);
    expect(exon.x).toBeCloseTo(((1381887 - 1381622) / 1841) * 600, 6);
    expect(exon.width).toBeCloseTo((158 / 1841) * 600, 6);
  });

  it("keeps a one-base box at least one unit wide", () => {
    expect(placeBox({ start: 5, end: 5 }, [1, 100000], 600).width).toBe(1);
  });
});
