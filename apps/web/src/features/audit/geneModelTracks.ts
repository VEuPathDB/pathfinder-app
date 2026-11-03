import type { FindingModels } from "@pathfinder/shared/generated/types/FindingModels";
import type { KeptIntron } from "@pathfinder/shared/generated/types/KeptIntron";
import type { ModelSpans } from "@pathfinder/shared/generated/types/ModelSpans";
import type { ProposedModel } from "@pathfinder/shared/generated/types/ProposedModel";
import type { Span } from "@pathfinder/shared/generated/types/Span";

import { percent } from "./format";
import { boxText } from "./geneModelWords";

export interface Box {
  start: number;
  end: number;
}

export interface ModelRow {
  label: string;
  strand: "+" | "-";
  exons: Box[];
  cds: Box[];
  introns: Box[];
  changed: Box[];
  codedOnly: Box[];
  unsupported: Box[];
  kept: Box[];
  junctions: { box: Box; reads: number | null }[];
  notes: string[];
  span: Box | null;
  stop: Box[];
}

export interface Track {
  seqid: string;
  window: [number, number];
  rows: ModelRow[];
}

interface SequenceRow {
  seqid: string;
  row: ModelRow;
}

function boxes(spans: readonly Span[]): Box[] {
  return spans
    .map(([start, end]) => ({ start, end }))
    .sort((left, right) => left.start - right.start);
}

function gaps(exons: Box[]): Box[] {
  return exons.slice(1).flatMap((exon, index) => {
    const before = exons[index];
    return before === undefined || exon.start <= before.end + 1
      ? []
      : [{ start: before.end + 1, end: exon.start - 1 }];
  });
}

function subtract(from: Box[], taken: Box[]): Box[] {
  return from.flatMap((box) => {
    const left: Box[] = [];
    let next = box.start;
    for (const cut of taken) {
      if (cut.end < next || cut.start > box.end) continue;
      if (cut.start > next) left.push({ start: next, end: cut.start - 1 });
      next = cut.end + 1;
    }
    return next <= box.end ? [...left, { start: next, end: box.end }] : left;
  });
}

function union(lists: Box[][]): Box[] {
  const sorted = lists.flat().sort((left, right) => left.start - right.start);
  return sorted.reduce<Box[]>((merged, box) => {
    const last = merged[merged.length - 1];
    if (last === undefined || box.start > last.end + 1) return [...merged, box];
    return [
      ...merged.slice(0, -1),
      { start: last.start, end: Math.max(last.end, box.end) },
    ];
  }, []);
}

export function changedSpans(
  annotated: Box[],
  proposed: Box[],
): { annotated: Box[]; proposed: Box[] } {
  return {
    annotated: subtract(annotated, proposed),
    proposed: subtract(proposed, annotated),
  };
}

function emptyRow(label: string, strand: ModelRow["strand"]): ModelRow {
  return {
    label,
    strand,
    exons: [],
    cds: [],
    introns: [],
    changed: [],
    codedOnly: [],
    unsupported: [],
    kept: [],
    junctions: [],
    notes: [],
    span: null,
    stop: [],
  };
}

function modelRow(label: string, model: ModelSpans): ModelRow {
  const exons = boxes(model.exons);
  return {
    ...emptyRow(label, model.strand),
    exons,
    cds: boxes(model.cds),
    introns: gaps(exons),
  };
}

function keptEvidence(kept: KeptIntron): string {
  if (kept.outcome === "NONCANONICAL") {
    return `splice-site bases ${kept.motif ?? "not stored"}`;
  }
  if (kept.depthShare === null || kept.coveredShare === null) {
    return "the depth over the intron is not stored";
  }
  return (
    `median depth ${percent(kept.depthShare)} of the exons', ` +
    `${percent(kept.coveredShare)} of its bases covered (${kept.track ?? "track not stored"})`
  );
}

function keptNote(kept: KeptIntron): string {
  return `intron kept as exon at ${boxText(kept)}: ${keptEvidence(kept)}`;
}

function proposedRow(
  proposed: ProposedModel,
  model: ModelSpans,
  codedOnly: Box[],
): ModelRow {
  const exons = boxes(proposed.exons);
  const kept = proposed.kept ?? [];
  const retained = proposed.kind === "retained";
  return {
    ...emptyRow(
      retained
        ? "Intron kept as exon (the RNA-seq does not splice it)"
        : "Proposed by RNA-seq evidence",
      model.strand,
    ),
    exons,
    cds: boxes(proposed.cds),
    introns: gaps(exons),
    changed: retained ? subtract(exons, boxes(model.exons)) : codedOnly,
    codedOnly,
    kept: kept.map(({ start, end }) => ({ start, end })),
    junctions: proposed.junctions.map(([start, end], index) => ({
      box: { start, end },
      reads: proposed.junctionReads[index] ?? null,
    })),
    notes: kept.map(keptNote),
  };
}

function intronRows(models: FindingModels): SequenceRow[] {
  return models.annotated.slice(0, 1).flatMap((model) => {
    const annotated = modelRow(`Annotated ${model.gene}, ${model.transcript}`, model);
    const { seqid } = model;
    const proposed = models.proposed ?? null;
    if (proposed === null) return [{ seqid, row: annotated }];
    const coded =
      proposed.kind === "corrected"
        ? changedSpans(annotated.cds, boxes(proposed.cds))
        : { annotated: [], proposed: [] };
    const unsupported = boxes(proposed.removedIntrons);
    return [
      {
        seqid,
        row: {
          ...annotated,
          changed: union([coded.annotated, unsupported]),
          codedOnly: coded.annotated,
          unsupported,
        },
      },
      { seqid, row: proposedRow(proposed, model, coded.proposed) },
    ];
  });
}

function labelled(models: FindingModels, label: (model: ModelSpans) => string) {
  return models.annotated.map((model) => ({
    seqid: model.seqid,
    row: modelRow(label(model), model),
  }));
}

function pairRows(models: FindingModels, first: string, second: string): SequenceRow[] {
  const [lead] = models.annotated;
  return labelled(models, (model) => {
    if (models.annotated.length < 2) return `Model ${model.gene}`;
    return `${model === lead ? first : second} ${model.gene}`;
  });
}

function mergeRows(models: FindingModels): SequenceRow[] {
  const merged = models.merged ?? null;
  const genes = pairRows(models, "Reference", "Partner");
  if (merged === null) return genes;
  return [
    {
      seqid: merged.seqid,
      row: {
        ...emptyRow(`Merged model ${merged.gene}`, merged.strand),
        span: { start: merged.start, end: merged.end },
      },
    },
    ...genes,
  ];
}

function selenoproteinRows(models: FindingModels): SequenceRow[] {
  const stop = models.stop;
  return models.annotated.map((model) =>
    model.gene === stop?.gene
      ? {
          seqid: model.seqid,
          row: {
            ...modelRow(`Model ${model.gene}`, model),
            stop: boxes(stop.spans),
          },
        }
      : {
          seqid: model.seqid,
          row: modelRow(`Reference ${model.gene}`, model),
        },
  );
}

function sequenceRows(models: FindingModels): SequenceRow[] {
  switch (models.kind) {
    case "intron":
      return intronRows(models);
    case "length":
      return labelled(models, (model) => `Annotated ${model.gene}`);
    case "pseudogene":
      return labelled(models, (model) => `Reference ${model.gene}`);
    case "strain":
      return pairRows(models, "Strain model", "Reference model");
    case "merge":
      return mergeRows(models);
    case "sec_end":
      return selenoproteinRows(models);
  }
}

function windowOf(rows: ModelRow[]): [number, number] {
  const all = rows.flatMap((row) => [
    ...row.exons,
    ...row.cds,
    ...row.stop,
    ...(row.span === null ? [] : [row.span]),
  ]);
  return [
    Math.min(...all.map((box) => box.start)),
    Math.max(...all.map((box) => box.end)),
  ];
}

export function geneModelTracks(models: FindingModels): Track[] {
  const placed = sequenceRows(models);
  const seqids = [...new Set(placed.map((entry) => entry.seqid))];
  return seqids.map((seqid) => {
    const rows = placed.filter((entry) => entry.seqid === seqid).map(({ row }) => row);
    return { seqid, window: windowOf(rows), rows };
  });
}

export function placeBox(
  box: Box,
  window: [number, number],
  width: number,
): { x: number; width: number } {
  const [low, high] = window;
  const scale = width / (high - low + 1);
  return {
    x: (box.start - low) * scale,
    width: Math.max(1, (box.end - box.start + 1) * scale),
  };
}
