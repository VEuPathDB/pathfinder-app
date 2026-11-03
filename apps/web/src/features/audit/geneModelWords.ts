import { joinWords, plural } from "./format";
import type { Box, ModelRow } from "./geneModelTracks";

export function baseText(base: number): string {
  return base.toLocaleString("en-US");
}

export function boxText(box: Box): string {
  return `${baseText(box.start)} to ${baseText(box.end)}`;
}

export function readsText(reads: number | null): string {
  return reads === null ? "reads not stored" : plural(reads, "read");
}

function boxesText(boxes: Box[]): string {
  return joinWords(boxes.map(boxText));
}

function stated(words: string, boxes: Box[]): string[] {
  return boxes.length === 0 ? [] : [`${words}${boxesText(boxes)}`];
}

function junctionText({ box, reads }: ModelRow["junctions"][number]): string {
  return `${boxText(box)} (${readsText(reads)})`;
}

export function rowText(row: ModelRow): string {
  const head = `${row.label}, ${row.strand} strand: `;
  if (row.span !== null) return `${head}one model over bases ${boxText(row.span)}`;
  const parts = [
    `${plural(row.exons.length, "exon")} at ${boxesText(row.exons)}`,
    ...stated("coded bases ", row.cds),
    ...stated("coded only here: ", row.codedOnly),
    ...stated("intron the RNA-seq does not support: ", row.unsupported),
    ...(row.junctions.length === 0
      ? []
      : [`RNA-seq reads join bases ${joinWords(row.junctions.map(junctionText))}`]),
    ...row.notes,
    ...stated("last coded codon at bases ", row.stop),
  ];
  return `${head}${parts.join("; ")}`;
}
