"use client";

import type { ReactElement } from "react";
import type { ControlSetEvidence, EvidenceCard } from "@pathfinder/shared";

import { EvidenceCardBody } from "@/features/conversation/rail/EvidenceCardBody";
import {
  requirementCountLine,
  sampleCountLine,
} from "@/features/conversation/rail/EvidenceReview";
import { Figure } from "@/features/conversation/thread/Figure";

function setClause(set: ControlSetEvidence | null | undefined, kind: string): string[] {
  if (set == null) return [];
  return [`${set.returnedCount} of ${set.controlsCount} ${kind} controls returned`];
}

/** The counts the card holds, in one sentence under the figure. */
function caption(card: EvidenceCard): string {
  const rows = card.review?.requirements ?? [];
  const genes = card.review?.sampledGenes ?? [];
  const clauses = [
    ...(rows.length > 0 ? [requirementCountLine(rows)] : []),
    ...(genes.length > 0 ? [sampleCountLine(genes)] : []),
    ...card.controls.flatMap((test) => [
      ...setClause(test.positive, "positive"),
      ...setClause(test.negative, "negative"),
    ]),
  ];
  const noun = card.steps.length === 1 ? "step" : "steps";
  const steps = {
    read: `${card.steps.length} ${noun} counted on the site`,
    not_answered: "the site did not answer the count read",
    not_read: "the strategy is not on the site yet",
  }[card.siteRead];
  return `${[...clauses, steps].join(", ")}.`;
}

/** The evidence behind one check, under the check in the thread. */
export function DataEvidenceCard({ data }: { data: EvidenceCard }): ReactElement {
  return (
    <Figure testId="data-evidence-card" title="Evidence" caption={caption(data)}>
      <EvidenceCardBody card={data} />
    </Figure>
  );
}
