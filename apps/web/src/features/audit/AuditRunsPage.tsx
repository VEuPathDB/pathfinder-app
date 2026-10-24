"use client";

import Link from "next/link";
import { useSuspenseQuery } from "@tanstack/react-query";
import { siteShortName } from "@pathfinder/shared";
import { listAuditRunsSuspenseQueryOptions } from "@pathfinder/shared/generated/hooks/useListAuditRunsSuspense";
import type { AuditRunSummary } from "@pathfinder/shared/generated/types/AuditRunSummary";
import type { CheckWords } from "@pathfinder/shared/generated/types/CheckWords";

import { auditWordsOptions } from "@/lib/api/audits";
import { QueryBoundary } from "@/lib/components/QueryBoundary";
import { auditRunUrl } from "@/lib/routes";

import { dayText, scopeText } from "./format";
import { PHASE_WORDS } from "./words";

export function AuditRunsPage({ lockedSite }: { lockedSite: string | null }) {
  return (
    <QueryBoundary>
      <RunsList lockedSite={lockedSite} />
    </QueryBoundary>
  );
}

function RunRow({
  run,
  checks,
  showSite,
}: {
  run: AuditRunSummary;
  checks: CheckWords;
  showSite: boolean;
}) {
  return (
    <tr className="border-t border-border">
      <td className="py-2 pr-4">
        <Link
          href={auditRunUrl(run.id)}
          aria-label={`Open the audit of ${scopeText(run)}, started ${dayText(run.createdAt)}`}
          className="text-primary underline-offset-2 hover:underline"
        >
          {dayText(run.createdAt)}
        </Link>
      </td>
      {showSite ? <td className="py-2 pr-4">{siteShortName(run.siteId)}</td> : null}
      <td className="py-2 pr-4">{scopeText(run)}</td>
      <td className="py-2 pr-4">
        {run.checks.map((check) => checks[check]).join("; ")}
      </td>
      <td className="py-2">{PHASE_WORDS[run.phase]}</td>
    </tr>
  );
}

function emptyText(lockedSite: string | null): string {
  const where = lockedSite === null ? "" : ` on ${siteShortName(lockedSite)}`;
  return `No audits${where} yet. Ask the audit assistant in a conversation to audit a genome.`;
}

function RunsList({ lockedSite }: { lockedSite: string | null }) {
  const { data: runs } = useSuspenseQuery(
    listAuditRunsSuspenseQueryOptions({ siteId: lockedSite }),
  );
  const { data: words } = useSuspenseQuery(auditWordsOptions());
  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="border-b border-border px-6 py-4">
        <h1 className="text-lg font-semibold">Audits</h1>
        <p className="mt-1 text-xs text-muted-foreground">
          Each audit checks the gene models a VEuPathDB site serves for the genomes you
          chose.
        </p>
      </header>
      <div className="min-h-0 flex-1 overflow-auto px-6 py-4">
        {runs.length === 0 ? (
          <p className="rounded border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
            {emptyText(lockedSite)}
          </p>
        ) : (
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Your audits, newest first</caption>
            <thead>
              <tr>
                <th scope="col">Started</th>
                {lockedSite === null ? <th scope="col">Site</th> : null}
                <th scope="col">What it examines</th>
                <th scope="col">Checks</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <RunRow
                  key={run.id}
                  run={run}
                  checks={words.checks}
                  showSite={lockedSite === null}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
