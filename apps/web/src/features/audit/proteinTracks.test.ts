import { describe, expect, it } from "vitest";
import type { GeneEvidence } from "@strategist/shared/generated/types/GeneEvidence";

import {
  organelleConfirmation,
  pseudogeneConfirmation,
  strainConfirmation,
} from "./__fixtures__/sampleConfirmations";
import { confirmationTracks, evidenceTracks, placeTracks } from "./proteinTracks";

const K13_EXCERPT: GeneEvidence = {
  geneIds: [{ given: "PF3D7_1343700", resolved: "PF3D7_1343700" }],
  gene: "PF3D7_1343700",
  pdbHits: [],
  peptides: [
    {
      transcript: "PF3D7_1343700.1",
      sequence: "TKANSISNFSMTYDR",
      start: 8,
      end: 22,
      experiments: ["Blood stage phospho- and total proteome (3D7)"],
      spectra: 1,
    },
    {
      transcript: "PF3D7_1343700.1",
      sequence: "ANSISNFSMTYDR",
      start: 10,
      end: 22,
      experiments: [
        "Blood stage phospho- and total proteome (3D7)",
        "Phosphorylation in the Plasmodium falciparum proteome (meta-analysis)",
      ],
      spectra: 59,
    },
  ],
  alphafold: [
    {
      uniprotId: "Q8IDQ2",
      source: "SWISSPROT direct link",
      first: 1,
      last: 726,
      length: 726,
    },
  ],
  linkouts: [],
  seqedits: [],
  transcripts: [
    {
      transcriptId: "PF3D7_1343700.1",
      transcriptType: "mRNA",
      proteinLength: 726,
      exonCount: 1,
    },
  ],
  comments: 9,
  pubmed: 44,
  notes: 2,
  phenotypes: [],
  unprefixedTables: [],
  unserved: [],
};

describe("confirmationTracks", () => {
  it("draws a strain pair to one scale with the run the strain lacks", () => {
    const tracks = confirmationTracks(strainConfirmation());
    expect(tracks.map((track) => [track.label, track.length, track.marks])).toEqual([
      ["Reference model PCYB_074210", 341, [{ kind: "missing", first: 41, last: 100 }]],
      ["Strain model PcyM_0736700", 280, []],
    ]);
    const [reference, strain] = placeTracks(tracks, 600);
    expect(reference?.width).toBe(600);
    expect(strain?.width).toBeCloseTo(492.669, 3);
    expect(reference?.marks[0]?.x).toBeCloseTo(70.381, 3);
    expect(reference?.marks[0]?.width).toBeCloseTo(105.572, 3);
  });

  it("marks the run only the strain holds on the strain's track", () => {
    const stored = strainConfirmation();
    const tracks = confirmationTracks({
      ...stored,
      result: { ...stored.result, extra: [[12, 30]] },
    });
    expect(tracks[1]?.marks).toEqual([{ kind: "extra", first: 12, last: 30 }]);
  });

  it("draws a pseudogene call's two sequences as codons with no stop inside", () => {
    const tracks = confirmationTracks(pseudogeneConfirmation());
    expect(tracks.map((track) => [track.label, track.length, track.marks])).toEqual([
      ["Reference PF3D7_1032400, translated codons", 462, []],
      [
        "Strain PfNF54_100037200, rebuilt through the reference, translated codons",
        462,
        [],
      ],
    ]);
    expect(tracks[0]?.summary).toBe(
      "Reference PF3D7_1032400, translated codons: 462 codons",
    );
  });

  it("marks a premature stop on the rebuilt strain sequence only", () => {
    const stored = pseudogeneConfirmation();
    const tracks = confirmationTracks({
      ...stored,
      result: { ...stored.result, prematureStops: [163] },
    });
    expect(tracks.map((track) => track.marks)).toEqual([
      [],
      [{ kind: "stop", first: 163, last: 163 }],
    ]);
  });

  it("counts only whole codons in a sequence not divisible by three", () => {
    const stored = pseudogeneConfirmation();
    const tracks = confirmationTracks({
      ...stored,
      result: { ...stored.result, referenceCdsLength: 1385, strainCdsLength: 1384 },
    });
    expect(tracks.map((track) => track.length)).toEqual([461, 461]);
  });

  it("carries that a stop list holds only the first stops", () => {
    const stored = pseudogeneConfirmation();
    const tracks = confirmationTracks({
      ...stored,
      result: {
        ...stored.result,
        prematureStops: [163],
        prematureStopsTruncated: true,
      },
    });
    expect(tracks.map((track) => track.stopsCut)).toEqual([false, true]);
  });

  it("draws nothing for a check that stores no residue coordinate of both models", () => {
    expect(confirmationTracks(organelleConfirmation())).toEqual([]);
  });
});

describe("evidenceTracks", () => {
  it("places the peptides and the structure the site serves on the transcript's protein", () => {
    const tracks = evidenceTracks(K13_EXCERPT);
    expect(
      tracks.map((track) => [
        track.label,
        track.length,
        track.marks.map((mark) => [mark.kind, mark.first, mark.last]),
      ]),
    ).toEqual([
      [
        "PF3D7_1343700.1, 726 residues",
        726,
        [
          ["structure", 1, 726],
          ["peptide", 8, 22],
          ["peptide", 10, 22],
        ],
      ],
    ]);
    const [placed] = placeTracks(tracks, 600);
    expect(placed?.marks[1]?.x).toBeCloseTo(5.785, 3);
    expect(placed?.marks[1]?.width).toBeCloseTo(12.397, 3);
  });

  it("places a peptide only on the transcript it was read on", () => {
    const [first, second] = evidenceTracks({
      ...K13_EXCERPT,
      alphafold: [],
      transcripts: [
        ...K13_EXCERPT.transcripts,
        {
          transcriptId: "PF3D7_1343700.2",
          transcriptType: "mRNA",
          proteinLength: 726,
          exonCount: 1,
        },
      ],
    });
    expect(first?.marks).toHaveLength(2);
    expect(second?.marks).toEqual([]);
  });

  it("leaves out a transcript with no served protein and a structure of another length", () => {
    const tracks = evidenceTracks({
      ...K13_EXCERPT,
      peptides: [],
      alphafold: [
        {
          uniprotId: "Q8IDQ2",
          source: "SWISSPROT direct link",
          first: 1,
          last: 700,
          length: 700,
        },
      ],
      transcripts: [
        ...K13_EXCERPT.transcripts,
        {
          transcriptId: "PF3D7_1343700.2",
          transcriptType: "ncRNA",
          proteinLength: null,
          exonCount: 1,
        },
      ],
    });
    expect(tracks.map((track) => [track.label, track.marks])).toEqual([
      ["PF3D7_1343700.1, 726 residues", []],
    ]);
  });
});

describe("placeTracks", () => {
  it("keeps a one-residue mark at least one unit wide", () => {
    const [placed] = placeTracks(
      [
        {
          label: "One long protein",
          length: 5000,
          summary: "One long protein: 5,000 residues",
          stopsCut: false,
          marks: [{ kind: "stop", first: 2500, last: 2500 }],
        },
      ],
      600,
    );
    expect(placed?.marks[0]?.width).toBe(1);
  });
});
