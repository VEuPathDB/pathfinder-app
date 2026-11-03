import { joinWords, plural } from "./format";
import type { Box, ModelRow } from "./geneModelTracks";

export function baseText(base: number): string {
  return base.toLocaleString("en-US");
}

function boxText(box: Box): string {
  return `${baseText(box.start)} to ${baseText(box.end)}`;
}

function boxesText(boxes: Box[]): string {
  return joinWords(boxes.map(boxText));
}

function stated(words: string, boxes: Box[]): string[] {
  return boxes.length === 0 ? [] : [`${words}${boxesText(boxes)}`];
}

function partCount(row: ModelRow): string {
  return row.proposal && row.cds.length > 0
    ? plural(row.cds.length, "coded part")
    : plural(row.exons.length, "exon");
}

function codedBases(row: ModelRow): string[] {
  return stated("coded bases ", row.cds);
}

function junctionText({ box, reads }: ModelRow["junctions"][number]): string {
  return `${boxText(box)} (${plural(reads, "read")})`;
}

export function rowText(row: ModelRow): string {
  const head = `${row.label}, ${row.strand} strand: `;
  if (row.span !== null) return `${head}one model over bases ${boxText(row.span)}`;
  const parts = [
    partCount(row),
    ...(row.proposal ? [] : codedBases(row)),
    ...stated("coded only here: ", row.codedOnly),
    ...stated("intron the RNA-seq does not support: ", row.unsupported),
    ...(row.proposal ? codedBases(row) : []),
    ...stated("intron kept as exon: ", row.kept),
    ...(row.junctions.length === 0
      ? []
      : [`RNA-seq reads join bases ${joinWords(row.junctions.map(junctionText))}`]),
    ...row.notes,
    ...stated("stop codon at bases ", row.stop),
  ];
  return `${head}${parts.join("; ")}`;
}
