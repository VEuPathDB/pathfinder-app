"use client";

import type { VariantComparison, VariantResult } from "@pathfinder/shared";
import { z } from "zod";

import {
  ExhibitTable,
  type ExhibitNote,
  type ExhibitRow,
} from "@/features/conversation/thread/ExhibitTable";
import { Figure } from "@/features/conversation/thread/Figure";

import { useChatHelpers } from "../../runtime/chatHelpersContext";
import { tableNumberFor } from "./tableNumbers";

const TRUNCATED_NOTE = "large results, overlap is a lower bound";

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

function rows(data: VariantComparison): ExhibitRow[] {
  const counted = countedInTheResult(data);
  return data.variants.map((variant) => ({
    key: variant.label,
    cells: [
      variantLabel(variant),
      hasFailed(variant) ? "-" : variant.geneCount.toLocaleString(),
      hasFailed(variant) ? "-" : variant.uniqueCount.toLocaleString(),
      ...(counted ? [variant.resultCount?.toLocaleString() ?? "-"] : []),
    ],
  }));
}

/** Why a variant has no counts, which genes only it returned, and how far the
 * pairs overlap. */
function notes(data: VariantComparison): ExhibitNote[] {
  const built: ExhibitNote[] = [];
  if (data.truncated === true) {
    built.push({ key: "truncated", label: "Note:", body: TRUNCATED_NOTE });
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
        body: <span className="font-mono">{variant.sampleUniqueGenes.join(", ")}</span>,
      });
    }
  }
  for (const overlap of data.overlaps) {
    built.push({
      key: `${overlap.a}|${overlap.b}`,
      label: `${overlap.a} vs ${overlap.b}:`,
      body: `${overlap.shared.toLocaleString()} shared, Jaccard ${String(overlap.jaccard)}`,
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
