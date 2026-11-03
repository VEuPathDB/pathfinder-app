"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useSuspenseQuery } from "@tanstack/react-query";

import { auditWordsOptions } from "@/lib/api/audits";
import { QueryBoundary } from "@/lib/components/QueryBoundary";
import { auditRunUrl, auditsUrl } from "@/lib/routes";

import { auditRunOptions, isLiveRun } from "./api";
import { DownloadFindings } from "./DownloadFindings";
import { FindingFilters } from "./FindingFilters";
import {
  type FindingFilterState,
  filtersFromSearch,
  searchFromFilters,
} from "./findingQuery";
import { FindingsList } from "./FindingsList";
import { RateChart } from "./RateChart";
import { RateHeatMap } from "./RateHeatMap";
import { RateTable } from "./RateTable";
import { ReportSummary } from "./ReportSummary";
import { RunAction } from "./RunAction";
import { RunHeader } from "./RunHeader";
import { StageProgress } from "./StageProgress";
import { TargetReport } from "./TargetReport";

export function AuditRunPage({ runId }: { runId: string }) {
  return (
    <QueryBoundary>
      <RunPage runId={runId} />
    </QueryBoundary>
  );
}

function RunPage({ runId }: { runId: string }) {
  const { data: view } = useSuspenseQuery(auditRunOptions(runId));
  const { data: words } = useSuspenseQuery(auditWordsOptions());
  const router = useRouter();
  const state = filtersFromSearch(new URLSearchParams(useSearchParams().toString()));
  const search = searchFromFilters(state);
  const live = isLiveRun(view);
  const go = (next: FindingFilterState) => {
    router.replace(auditRunUrl(runId, searchFromFilters(next)), { scroll: false });
  };
  const total = view.counts.reduce((sum, row) => sum + row.count, 0);
  return (
    <div className="h-full overflow-auto px-6 py-4">
      <nav className="mb-3 text-sm">
        <Link
          href={auditsUrl()}
          className="text-primary underline-offset-2 hover:underline"
        >
          All audits
        </Link>
      </nav>
      <RunHeader view={view} words={words} />
      <StageProgress view={view} words={words} />
      <RunAction view={view} />
      <ReportSummary view={view} />
      {view.rates.length > 0 && (
        <section aria-labelledby="audit-rates" className="mt-6">
          <h2 id="audit-rates" className="text-base font-semibold">
            Error rates
          </h2>
          <RateHeatMap view={view} words={words} />
          <RateChart rates={view.rates} checks={words.checks} />
          <RateTable view={view} words={words} />
        </section>
      )}
      {(view.targets.genomes.length > 0 || view.targets.unplaced > 0) && (
        <TargetReport report={view.targets} words={words} />
      )}
      <section aria-labelledby="audit-findings" className="mt-6">
        <div className="flex items-center justify-between">
          <h2 id="audit-findings" className="text-base font-semibold">
            Findings
          </h2>
          <DownloadFindings runId={runId} total={total} />
        </div>
        <FindingFilters view={view} words={words} state={state} onChange={go} />
        <QueryBoundary resetKeys={[search]}>
          <FindingsList
            runId={runId}
            words={words}
            state={state}
            search={search}
            live={live}
            onPage={(offset) => {
              go({ ...state, offset });
            }}
          />
        </QueryBoundary>
      </section>
    </div>
  );
}
