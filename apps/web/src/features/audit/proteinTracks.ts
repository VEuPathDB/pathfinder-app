import type { ConfirmationEvidence } from "@pathfinder/shared/generated/types/ConfirmationEvidence";
import type { FindingDetail } from "@pathfinder/shared/generated/types/FindingDetail";
import type { GeneEvidence } from "@pathfinder/shared/generated/types/GeneEvidence";
import type { GeneTranscript } from "@pathfinder/shared/generated/types/GeneTranscript";

export type ProteinMarkKind = "missing" | "extra" | "stop" | "peptide" | "structure";

export interface ProteinMark {
  kind: ProteinMarkKind;
  first: number;
  last: number;
}

export interface ProteinTrack {
  label: string;
  summary: string;
  length: number;
  stopsCut: boolean;
  marks: ProteinMark[];
}

export interface PlacedMark extends ProteinMark {
  x: number;
  width: number;
}

export interface PlacedTrack extends Omit<ProteinTrack, "marks"> {
  width: number;
  marks: PlacedMark[];
}

const CODON = 3;

function runs(kind: ProteinMarkKind, spans: [number, number][]): ProteinMark[] {
  return spans.map(([first, last]) => ({ kind, first, last }));
}

function statedTrack(
  label: string,
  length: number,
  unit: string,
  marks: ProteinMark[],
  stopsCut = false,
): ProteinTrack {
  const summary = `${label}: ${length.toLocaleString("en-US")} ${unit}`;
  return { label, summary, length, stopsCut, marks };
}

export function confirmationTracks(
  confirmation: ConfirmationEvidence["confirmation"],
): ProteinTrack[] {
  switch (confirmation.check) {
    case "strain_model": {
      const { result } = confirmation;
      return [
        statedTrack(
          `Reference model ${result.referenceGene}`,
          result.referenceLength,
          "residues",
          runs("missing", result.lost),
        ),
        statedTrack(
          `Strain model ${result.strainGene}`,
          result.strainLength,
          "residues",
          runs("extra", result.extra),
        ),
      ];
    }
    case "pseudogene_call": {
      const { result } = confirmation;
      return [
        statedTrack(
          `Reference ${result.referenceGene}, translated codons`,
          Math.floor(result.referenceCdsLength / CODON),
          "codons",
          [],
        ),
        statedTrack(
          `Strain ${result.strainGene}, rebuilt through the reference, translated codons`,
          Math.floor(result.strainCdsLength / CODON),
          "codons",
          result.prematureStops.map((stop) => ({
            kind: "stop",
            first: stop,
            last: stop,
          })),
          result.prematureStopsTruncated === true,
        ),
      ];
    }
    case "gene_fusion":
    case "gene_length":
    case "gene_split":
    case "intron_support":
    case "missing_gene":
    case "organelle_join":
    case "selenoprotein_end":
      return [];
  }
}

export function findingTracks(detail: FindingDetail): ProteinTrack[] {
  return detail.evidence.flatMap(({ status, payload }) =>
    status === "stored" && payload?.kind === "confirmation"
      ? confirmationTracks(payload.confirmation)
      : [],
  );
}

export function tracksTitle(inCodons: boolean): string {
  return inCodons
    ? "Coding sequences of the two genes, in codons"
    : "Protein lengths of the two models";
}

function transcriptTrack(
  evidence: GeneEvidence,
  transcript: GeneTranscript,
  length: number,
): ProteinTrack {
  const structures = evidence.alphafold.filter((model) => model.length === length);
  const peptides = evidence.peptides.filter(
    (peptide) => peptide.transcript === transcript.transcriptId,
  );
  const label = `${transcript.transcriptId}, ${length.toLocaleString("en-US")} residues`;
  return {
    label,
    summary: label,
    length,
    stopsCut: false,
    marks: [
      ...structures.map((model): ProteinMark => ({
        kind: "structure",
        first: model.first,
        last: model.last,
      })),
      ...peptides.map((peptide): ProteinMark => ({
        kind: "peptide",
        first: peptide.start,
        last: peptide.end,
      })),
    ],
  };
}

export function evidenceTracks(evidence: GeneEvidence): ProteinTrack[] {
  return evidence.transcripts.flatMap((transcript) =>
    transcript.proteinLength === null
      ? []
      : [transcriptTrack(evidence, transcript, transcript.proteinLength)],
  );
}

export function placeTracks(tracks: ProteinTrack[], width: number): PlacedTrack[] {
  const longest = Math.max(1, ...tracks.map((track) => track.length));
  const scale = width / longest;
  return tracks.map((track) => ({
    ...track,
    width: track.length * scale,
    marks: track.marks.map((mark) => ({
      ...mark,
      x: (mark.first - 1) * scale,
      width: Math.max(1, (mark.last - mark.first + 1) * scale),
    })),
  }));
}
