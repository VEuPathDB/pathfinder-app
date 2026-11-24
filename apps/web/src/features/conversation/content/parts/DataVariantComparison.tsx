"use client";

import type { VariantComparison, VariantResult } from "@strategist/shared";
import { z } from "zod";

import {
  ExhibitTable,
  type ExhibitNote,
  type ExhibitRow,
} from "@/features/conversation/thread/ExhibitTable";
import { Figure } from "@/features/conversation/thread/Figure";

import { useChatHelpers } from "../../runtime/chatHelpersContext";
import { tableNumberFor } from "./tableNumbers";

function readCapNote(cap: number): string {
  const read = cap.toLocaleString();
  return `a variant past ${read} genes is read to its first ${read}, so "at least" marks a lower bound`;
}

const COLUMNS = [
  { head: "Variant" },
  { head: "Genes", numeric: true },
  { head: "Unique to it", numeric: true },
] as const;

/** The strategy's result with each variant in place, where the tool counted it. */
const RESULT_COLUMN = { head: "In the result", numeric: true } as const;

function countedInTheResult(data: VariantComparison): boolean {
  return data.variants.some((variant) => variant.resultCount != null);
}

function largestGeneCount(data: VariantComparison): number {
  return data.variants.reduce((best, variant) => Math.max(best, variant.geneCount), 0);
}

function hasFailed(variant: VariantResult): boolean {
  return variant.error != null && variant.error !== "";
}

/** A multi-pick wire value: a JSON list of strings. */
const WireList = z.array(z.string());

function wireValueText(raw: string): string {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return raw;
  }
  const list = WireList.safeParse(parsed);
  return list.success ? list.data.join(", ") : raw;
}

function variantLabel(variant: VariantResult) {
  const differs = Object.entries(variant.differsBy ?? {});
  return (
    <span key="label" className="flex flex-col">
      <span className="font-medium">{variant.label}</span>
      {differs.map(([name, value]) => (
        <span
          key={name}
          data-testid="variant-differs-by"
          className="text-xs text-muted-foreground"
        >
          {`${name}: ${wireValueText(value)}`}
        </span>
      ))}
    </span>
  );
}

type UniqueGene = VariantResult["sampleUniqueGenes"][number];

/** Each gene only one variant returned, one per line, with its product. */
function uniqueGenes(genes: readonly UniqueGene[]) {
  return (
    <span className="flex flex-col">
      {genes.map((gene) => (
        <span key={gene.geneId} data-testid="variant-unique-gene">
          <span className="font-mono">{gene.geneId}</span>
          {gene.product != null && gene.product !== "" ? ` ${gene.product}` : null}
        </span>
      ))}
    </span>
  );
}

function uniqueText(variant: VariantResult): string {
  if (hasFailed(variant)) return "-";
  if (variant.uniqueCount == null) return "not counted";
  const count = variant.uniqueCount.toLocaleString();
  return variant.uniqueAtLeast ? `at least ${count}` : count;
}

type Overlap = VariantComparison["overlaps"][number];

function overlapText(overlap: Overlap): string {
  const shared = overlap.shared.toLocaleString();
  if (overlap.jaccard == null) return `at least ${shared} shared`;
  return `${shared} shared, Jaccard ${String(overlap.jaccard)}`;
}

function rows(data: VariantComparison): ExhibitRow[] {
  const counted = countedInTheResult(data);
  return data.variants.map((variant) => ({
    key: variant.label,
    cells: [
      variantLabel(variant),
      hasFailed(variant) ? "-" : variant.geneCount.toLocaleString(),
      uniqueText(variant),
      ...(counted ? [variant.resultCount?.toLocaleString() ?? "-"] : []),
    ],
  }));
}

/** Why a variant has no counts, which genes only it returned, and how far the
 * pairs overlap. */
function notes(data: VariantComparison): ExhibitNote[] {
  const built: ExhibitNote[] = [];
  if (data.readCap != null) {
    built.push({ key: "read-cap", label: "Note:", body: readCapNote(data.readCap) });
  }
  for (const variant of data.variants) {
    if (hasFailed(variant)) {
      built.push({
        key: `failed-${variant.label}`,
        label: `${variant.label}:`,
        body: (
          <span className="text-destructive">{`failed: ${variant.error ?? ""}`}</span>
        ),
      });
      continue;
    }
    if (variant.sampleUniqueGenes.length > 0) {
      built.push({
        key: `unique-${variant.label}`,
        label: `Only in ${variant.label}:`,
        body: uniqueGenes(variant.sampleUniqueGenes),
      });
    }
  }
  for (const overlap of data.overlaps) {
    built.push({
      key: `${overlap.a}|${overlap.b}`,
      label: `${overlap.a} vs ${overlap.b}:`,
      body: overlapText(overlap),
    });
  }
  return built;
}

export function DataVariantComparison({ data }: { data: VariantComparison }) {
  const chat = useChatHelpers();
  return (
    <Figure
      testId="data-variant-comparison"
      title="Variants"
      caption={`${data.variants.length.toLocaleString()} variants, ${largestGeneCount(data).toLocaleString()} genes in the largest`}
      exhibit={{ kind: "table", number: tableNumberFor(chat.messages, data) }}
    >
      <ExhibitTable
        columns={countedInTheResult(data) ? [...COLUMNS, RESULT_COLUMN] : COLUMNS}
        rows={rows(data)}
        notes={notes(data)}
      />
    </Figure>
  );
}
