"use client";

import Link from "next/link";
import { useSuspenseQuery } from "@tanstack/react-query";
import { listAuditFindingsSuspenseQueryOptions } from "@pathfinder/shared/generated/hooks/useListAuditFindingsSuspense";
import type { AuditWords } from "@pathfinder/shared/generated/types/AuditWords";
import type { FindingView } from "@pathfinder/shared/generated/types/FindingView";

import { Button } from "@/components/ui/button";
import { auditFindingUrl } from "@/lib/routes";

import { RUN_POLL_MS } from "./api";
import {
  FINDINGS_PAGE,
  type FindingFilterState,
  findingQuery,
  type Origin,
} from "./findingQuery";
import { impactText, joinWords } from "./format";
import { CERTAINTY_WORDS, ORIGIN_WORDS } from "./words";

export function findingOutcome(finding: FindingView, words: AuditWords): string {
  if (finding.effectiveErrorTitle !== null) return finding.effectiveErrorTitle;
  if (finding.status !== "confirmed") return words.findingStatuses[finding.status];
  return finding.judged ? "No error found" : "Not judged";
}

export function findingOrigin(finding: FindingView): Origin {
  if (finding.fromTarget) return "target";
  return finding.sampled ? "sample" : "unsampled";
}

export function genomeText(finding: FindingView): string {
  if (finding.genome === "") return "Not placed in a genome";
  const screened =
    finding.screenedGenome !== "" && finding.screenedGenome !== finding.genome
      ? ` (screened in ${finding.screenedGenome})`
      : "";
  const paired =
    finding.pairedGenome === null ? "" : `, paired with ${finding.pairedGenome}`;
  return `${finding.genome}${screened}${paired}`;
}

function impactCell(finding: FindingView): string {
  const reviewed = finding.reviewLine?.impact ?? null;
  const stored = impactText(finding.impact);
  return reviewed === null ? stored : `${stored} (reviewed ${String(reviewed)})`;
}

function FindingRow({
  runId,
  finding,
  words,
  search,
}: {
  runId: string;
  finding: FindingView;
  words: AuditWords;
  search: string;
}) {
  const genes = finding.genes.map((link) => link.gene);
  return (
    <tr className="border-t border-border">
      <td className="py-1 pr-4">{impactCell(finding)}</td>
      <td className="py-1 pr-4">{findingOutcome(finding, words)}</td>
      <td className="py-1 pr-4">{genes.join(", ")}</td>
      <td className="py-1 pr-4">{genomeText(finding)}</td>
      <td className="py-1 pr-4">
        {finding.certainty === null ? "" : CERTAINTY_WORDS[finding.certainty]}
      </td>
      <td className="py-1 pr-4">{ORIGIN_WORDS[findingOrigin(finding)]}</td>
      <td className="py-1 pr-4">{finding.reviewLine?.verdictText ?? "Not reviewed"}</td>
      <td className="py-1">
        <Link
          href={auditFindingUrl(runId, finding.id, search)}
          aria-label={`Open the finding on ${joinWords(genes)}`}
          className="text-primary underline-offset-2 hover:underline"
        >
          Open
        </Link>
      </td>
    </tr>
  );
}

export function FindingsList({
  runId,
  words,
  state,
  search,
  live,
  onPage,
}: {
  runId: string;
  words: AuditWords;
  state: FindingFilterState;
  search: string;
  live: boolean;
  onPage: (offset: number) => void;
}) {
  const { data: page } = useSuspenseQuery({
    ...listAuditFindingsSuspenseQueryOptions(runId, findingQuery(state)),
    refetchInterval: live ? RUN_POLL_MS : false,
  });
  const offset = state.offset;
  const shown = page.findings.length;
  return (
    <div className="mt-3 text-sm">
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <caption className="text-left font-medium">
            {`Findings, by the screen's impact: ${String(page.total)}`}
          </caption>
          <thead>
            <tr>
              <th scope="col">Screen impact</th>
              <th scope="col">Finding</th>
              <th scope="col">Genes</th>
              <th scope="col">Model&apos;s genome</th>
              <th scope="col">Certainty</th>
              <th scope="col">Source</th>
              <th scope="col">Review</th>
              <th scope="col">
                <span className="sr-only">Open</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {page.findings.map((finding) => (
              <FindingRow
                key={finding.id}
                runId={runId}
                finding={finding}
                words={words}
                search={search}
              />
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-2 flex items-center gap-3">
        <p>
          {shown === 0
            ? "No finding matches these filters."
            : `Showing ${String(offset + 1)} to ${String(offset + shown)} of ${String(page.total)}`}
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={offset === 0}
          onClick={() => {
            onPage(Math.max(offset - FINDINGS_PAGE, 0));
          }}
        >
          Previous page
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={offset + FINDINGS_PAGE >= page.total}
          onClick={() => {
            onPage(offset + FINDINGS_PAGE);
          }}
        >
          Next page
        </Button>
      </div>
    </div>
  );
}
