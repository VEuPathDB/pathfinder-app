"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useSuspenseQuery } from "@tanstack/react-query";
import { siteShortName } from "@pathfinder/shared";
import { getAuditFindingSuspenseQueryOptions } from "@pathfinder/shared/generated/hooks/useGetAuditFindingSuspense";
import type { AuditWords } from "@pathfinder/shared/generated/types/AuditWords";
import type { EvidenceViewKindEnumKey } from "@pathfinder/shared/generated/types/EvidenceView";
import type { FindingDetail } from "@pathfinder/shared/generated/types/FindingDetail";

import { auditWordsOptions } from "@/lib/api/audits";
import { QueryBoundary } from "@/lib/components/QueryBoundary";
import { auditRunUrl } from "@/lib/routes";

import { auditRunOptions } from "./api";
import { ConfirmationSection, GeneModelsSection } from "./ConfirmationSection";
import { findingOrigin, findingOutcome, genomeText } from "./FindingsList";
import { findingRequestsText } from "./format";
import { GeneEvidenceSection } from "./GeneEvidenceSection";
import { ImpactBreakdown } from "./ImpactBreakdown";
import { RelativesSection } from "./RelativesSection";
import { ReviewSection } from "./ReviewSection";
import { CERTAINTY_WORDS, ORIGIN_WORDS } from "./words";

const LINK = "text-primary underline-offset-2 hover:underline";

export function AuditFindingPage({
  runId,
  findingId,
}: {
  runId: string;
  findingId: string;
}) {
  const id = Number(findingId);
  if (!Number.isInteger(id) || id < 1) {
    return <p className="px-6 py-4 text-sm">This finding does not exist.</p>;
  }
  return (
    <QueryBoundary>
      <FindingPage runId={runId} findingId={id} />
    </QueryBoundary>
  );
}

function Evidence({ detail, words }: { detail: FindingDetail; words: AuditWords }) {
  const factsOf = (kind: EvidenceViewKindEnumKey) =>
    detail.facts.find((group) => group.kind === kind)?.facts ?? [];
  return (
    <section aria-labelledby="audit-evidence" className="mt-6 text-sm">
      <h2 id="audit-evidence" className="text-base font-semibold">
        Evidence
      </h2>
      {detail.evidence.length === 0 ? (
        <p className="mt-1">No evidence was read for this finding.</p>
      ) : null}
      {detail.evidence.map((evidence) => {
        const facts = factsOf(evidence.kind);
        switch (evidence.kind) {
          case "confirmation":
            return (
              <ConfirmationSection
                key={evidence.kind}
                detail={detail}
                evidence={evidence}
                facts={facts}
                words={words}
              />
            );
          case "relatives":
            return (
              <RelativesSection
                key={evidence.kind}
                detail={detail}
                evidence={evidence}
                facts={facts}
                words={words}
              />
            );
          case "gene_evidence":
            return (
              <GeneEvidenceSection
                key={evidence.kind}
                evidence={evidence}
                facts={facts}
                words={words}
              />
            );
        }
      })}
    </section>
  );
}

function FindingPage({ runId, findingId }: { runId: string; findingId: number }) {
  const { data: view } = useSuspenseQuery(auditRunOptions(runId));
  const { data: words } = useSuspenseQuery(auditWordsOptions());
  const { data: detail } = useSuspenseQuery(
    getAuditFindingSuspenseQueryOptions(runId, findingId),
  );
  const search = useSearchParams().toString();
  const { finding } = detail;
  const site = siteShortName(detail.siteId);
  const unjudged = finding.status === "confirmed" && !finding.judged;
  const requests = findingRequestsText(detail);
  return (
    <div className="h-full overflow-auto px-6 py-4">
      <nav className="mb-3 text-sm">
        <Link
          href={auditRunUrl(runId, search === "" ? "" : `?${search}`)}
          className={LINK}
        >
          Back to the audit
        </Link>
      </nav>
      <h1 className="text-lg font-semibold">{findingOutcome(finding, words)}</h1>
      <p className="mt-1 text-sm">{finding.checkTitle}</p>
      {unjudged ? (
        <p className="mt-1 text-sm">The check could not judge this candidate.</p>
      ) : null}
      <p className="mt-1 text-sm">{genomeText(finding)}</p>
      <ul aria-label="About this finding" className="mt-1 flex flex-wrap gap-3 text-sm">
        {finding.effectiveCertainty === null ? null : (
          <li>{CERTAINTY_WORDS[finding.effectiveCertainty]}</li>
        )}
        <li>{`Source: ${ORIGIN_WORDS[findingOrigin(finding)]}`}</li>
        {requests === null ? null : <li>{requests}</li>}
      </ul>
      <ul className="mt-2 flex flex-wrap gap-3 text-sm">
        {detail.genes.map((link) => (
          <li key={link.gene}>
            <a
              href={link.url}
              target="_blank"
              rel="noreferrer"
              aria-label={`Open ${link.gene} in ${site}`}
              className={LINK}
            >
              {link.gene}
            </a>
          </li>
        ))}
      </ul>
      <ImpactBreakdown finding={finding} />
      <ReviewSection
        detail={detail}
        agreement={view.agreement}
        reviewState={view.reviewState}
        words={words}
      />
      <GeneModelsSection detail={detail} />
      <Evidence detail={detail} words={words} />
    </div>
  );
}
