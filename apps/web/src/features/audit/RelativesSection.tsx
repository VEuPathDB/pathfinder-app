"use client";

import { useId } from "react";
import type { ReactNode } from "react";
import type { AuditWords } from "@pathfinder/shared/generated/types/AuditWords";
import type { EvidenceView } from "@pathfinder/shared/generated/types/EvidenceView";
import type { Fact } from "@pathfinder/shared/generated/types/Fact";
import type { FindingDetail } from "@pathfinder/shared/generated/types/FindingDetail";

import { EvidenceNote } from "./EvidenceNote";
import { FactList } from "./FactList";
import { RelativesPlot } from "./RelativesPlot";
import { relativesOutcome } from "./relativesPoints";

export function EvidenceRegion({
  evidence,
  facts,
  words,
  lead = null,
  figures = null,
}: {
  evidence: EvidenceView;
  facts: readonly Fact[];
  words: AuditWords;
  lead?: string | null;
  figures?: ReactNode;
}) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="mt-3">
      <h3 id={headingId} className="font-medium">
        {words.evidenceKinds[evidence.kind]}
      </h3>
      {evidence.status === "stored" ? (
        <>
          {lead === null ? null : <p className="mt-1 text-sm">{lead}</p>}
          {figures}
          <FactList facts={facts} />
        </>
      ) : (
        <EvidenceNote evidence={evidence} words={words} />
      )}
    </section>
  );
}

export function RelativesSection({
  detail,
  evidence,
  facts,
  words,
}: {
  detail: FindingDetail;
  evidence: EvidenceView;
  facts: readonly Fact[];
  words: AuditWords;
}) {
  return (
    <EvidenceRegion
      evidence={evidence}
      facts={facts}
      words={words}
      figures={<RelativesPlot outcome={relativesOutcome(detail, words)} />}
    />
  );
}
