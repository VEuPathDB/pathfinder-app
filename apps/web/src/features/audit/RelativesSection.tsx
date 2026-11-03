"use client";

import { useId } from "react";
import type { AuditWords } from "@pathfinder/shared/generated/types/AuditWords";
import type { EvidenceView } from "@pathfinder/shared/generated/types/EvidenceView";
import type { Fact } from "@pathfinder/shared/generated/types/Fact";

import { EvidenceNote } from "./EvidenceNote";
import { FactList } from "./FactList";

export function EvidenceRegion({
  evidence,
  facts,
  words,
  lead = null,
}: {
  evidence: EvidenceView;
  facts: readonly Fact[];
  words: AuditWords;
  lead?: string | null;
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
          <FactList facts={facts} />
        </>
      ) : (
        <EvidenceNote evidence={evidence} words={words} />
      )}
    </section>
  );
}

export function RelativesSection({
  evidence,
  facts,
  words,
}: {
  evidence: EvidenceView;
  facts: readonly Fact[];
  words: AuditWords;
}) {
  return <EvidenceRegion evidence={evidence} facts={facts} words={words} />;
}
