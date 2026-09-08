"use client";

import type { ReactElement } from "react";

import type { ScoredComparison, ScoredVariant } from "@pathfinder/shared";

import {
  ExhibitTable,
  type ExhibitNote,
  type ExhibitRow,
} from "@/features/conversation/thread/ExhibitTable";
import { Figure } from "@/features/conversation/thread/Figure";

import { useChatHelpers } from "../../runtime/chatHelpersContext";
import { tableNumberFor } from "./tableNumbers";

const COLUMNS = [
  { head: "Variant" },
  { head: "MCC", numeric: true },
  { head: "F1", numeric: true },
  { head: "Precision", numeric: true },
  { head: "Sensitivity", numeric: true },
  { head: "Balanced accuracy", numeric: true },
] as const;

function fmt(value: number | null | undefined): string {
  return value == null ? "-" : value.toFixed(2);
}

function hasFailed(variant: ScoredVariant): boolean {
  return variant.error != null && variant.error !== "";
}

function caption(data: ScoredComparison): string {
  const count = `${data.variants.length.toLocaleString()} variants`;
  const winner = data.variants.find((v) => v.label === data.winnerLabel);
  if (data.winnerLabel != null && winner !== undefined) {
    return `${count}, winner ${data.winnerLabel} at ${fmt(winner.mcc)}`;
  }
  const failed = data.variants.filter(hasFailed).length;
  if (failed > 0) {
    return `scoring failed for ${failed.toLocaleString()} of ${count}`;
  }
  return `${count}, no winner`;
}

function Name({
  variant,
  isWinner,
}: {
  variant: ScoredVariant;
  isWinner: boolean;
}): ReactElement {
  return (
    <span className="flex items-baseline gap-1.5">
      <span className="font-medium">{variant.label}</span>
      {isWinner ? (
        <span className="text-[10px] font-medium text-primary">winner</span>
      ) : null}
    </span>
  );
}

function rows(data: ScoredComparison): ExhibitRow[] {
  return data.variants.map((variant) => {
    const isWinner = data.winnerLabel != null && variant.label === data.winnerLabel;
    return {
      key: variant.label,
      cells: [
        <Name key="name" variant={variant} isWinner={isWinner} />,
        fmt(variant.mcc),
        fmt(variant.f1),
        fmt(variant.precision),
        fmt(variant.sensitivity),
        fmt(variant.balancedAccuracy),
      ],
    };
  });
}

/** Why a variant has no scores, and which control genes it holds. */
function notes(data: ScoredComparison): ExhibitNote[] {
  const built: ExhibitNote[] = [];
  for (const variant of data.variants) {
    if (hasFailed(variant)) {
      built.push({
        key: `failed-${variant.label}`,
        label: `${variant.label}:`,
        body: (
          <span className="text-destructive">{`scoring failed: ${variant.error ?? ""}`}</span>
        ),
      });
    }
    built.push({
      key: `controls-${variant.label}`,
      label: `${variant.label}:`,
      body: <Membership variant={variant} />,
    });
  }
  return built;
}

/** The control genes a variant's result set holds, ids in the code face. */
function Membership({ variant }: { variant: ScoredVariant }): ReactElement {
  const hits = variant.controlHits ?? [];
  if (hits.length === 0) return <span>contains none of the control genes</span>;
  return (
    <span>
      contains <span className="font-mono">{hits.join(", ")}</span>
    </span>
  );
}

export function DataScoredComparison({ data }: { data: ScoredComparison }) {
  const chat = useChatHelpers();
  return (
    <Figure
      testId="data-scored-comparison"
      title="Scored variants"
      caption={caption(data)}
      exhibit={{ kind: "table", number: tableNumberFor(chat.messages, data) }}
    >
      <p className="mb-3 text-[11px] text-muted-foreground">
        {`ranked by ${data.objective}`}
      </p>
      <ExhibitTable columns={COLUMNS} rows={rows(data)} notes={notes(data)} />
    </Figure>
  );
}
