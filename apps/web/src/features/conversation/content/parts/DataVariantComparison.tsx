"use client";

import type { VariantComparison, VariantResult } from "@pathfinder/shared";

import {
  ExhibitTable,
  type ExhibitNote,
  type ExhibitRow,
} from "@/features/conversation/thread/ExhibitTable";
import { Figure } from "@/features/conversation/thread/Figure";

import { useChatHelpers } from "../../runtime/chatHelpersContext";
import { tableNumberFor } from "./tableNumbers";

const TRUNCATED_NOTE = "large result sets, overlap is a lower bound";

const COLUMNS = [
  { head: "Variant" },
  { head: "Genes", numeric: true },
  { head: "Unique to it", numeric: true },
] as const;

function largestGeneCount(data: VariantComparison): number {
  return data.variants.reduce((best, variant) => Math.max(best, variant.geneCount), 0);
}

function hasFailed(variant: VariantResult): boolean {
  return variant.error != null && variant.error !== "";
}

function rows(data: VariantComparison): ExhibitRow[] {
  return data.variants.map((variant) => ({
    key: variant.label,
    cells: [
      <span key="label" className="font-medium">
        {variant.label}
      </span>,
      hasFailed(variant) ? "-" : variant.geneCount.toLocaleString(),
      hasFailed(variant) ? "-" : variant.uniqueCount.toLocaleString(),
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
      <ExhibitTable columns={COLUMNS} rows={rows(data)} notes={notes(data)} />
    </Figure>
  );
}
