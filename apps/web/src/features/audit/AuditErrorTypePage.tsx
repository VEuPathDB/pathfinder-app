"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useSuspenseQuery } from "@tanstack/react-query";
import type { AuditRunView } from "@strategist/shared/generated/types/AuditRunView";
import type { AuditWords } from "@strategist/shared/generated/types/AuditWords";
import type { ErrorTypeView } from "@strategist/shared/generated/types/ErrorTypeView";

import { auditWordsOptions } from "@/lib/api/audits";
import { QueryBoundary } from "@/lib/components/QueryBoundary";
import { auditErrorTypeUrl, auditRunUrl } from "@/lib/routes";

import { auditRunOptions, isLiveRun } from "./api";
import { FindingFilters } from "./FindingFilters";
import {
  type FindingFilterState,
  filtersFromSearch,
  searchFromFilters,
} from "./findingQuery";
import { FindingsList } from "./FindingsList";
import { joinWords } from "./format";

const NOT_SUMMARIZED = "Not summarized yet";

export function AuditErrorTypePage({
  runId,
  errorType,
}: {
  runId: string;
  errorType: string;
}) {
  return (
    <QueryBoundary>
      <ErrorTypePage runId={runId} errorType={errorType} />
    </QueryBoundary>
  );
}

function confirmedText(words: AuditWords, type: ErrorTypeView) {
  if (type.confirmedBy !== null) return type.confirmedBy;
  const checks = (type.checks ?? []).map((check) => words.checks[check]);
  return `${joinWords(checks)}. ${NOT_SUMMARIZED}.`;
}

function ErrorTypePage({ runId, errorType }: { runId: string; errorType: string }) {
  const { data: view } = useSuspenseQuery(auditRunOptions(runId));
  const { data: words } = useSuspenseQuery(auditWordsOptions());
  const type = view.errorTypes.find((row) => row.errorType === errorType);
  return (
    <div className="h-full overflow-auto px-6 py-4">
      <nav className="mb-3 text-sm">
        <Link
          href={auditRunUrl(runId)}
          className="text-primary underline-offset-2 hover:underline"
        >
          Back to the audit
        </Link>
      </nav>
      {type === undefined ? (
        <p className="text-sm">This audit names no such error.</p>
      ) : (
        <NamedErrorType view={view} words={words} type={type} />
      )}
    </div>
  );
}

function NamedErrorType({
  view,
  words,
  type,
}: {
  view: AuditRunView;
  words: AuditWords;
  type: ErrorTypeView;
}) {
  const runId = view.run.id;
  const router = useRouter();
  const address = filtersFromSearch(new URLSearchParams(useSearchParams().toString()));
  const state: FindingFilterState = { ...address, errorType: type.errorType };
  const go = (next: FindingFilterState) => {
    const search = searchFromFilters({ ...next, errorType: null });
    router.replace(auditErrorTypeUrl(runId, type.errorType, search), { scroll: false });
  };
  const live = isLiveRun(view);
  const search = searchFromFilters(state);
  return (
    <article className="text-sm">
      <h1 className="text-lg font-semibold">{type.title}</h1>
      {view.agreement === null ? null : <p className="mt-1">{view.agreement.text}</p>}
      <h2 className="mt-4 text-base font-semibold">What it is</h2>
      <p>{type.description}</p>
      <h2 className="mt-4 text-base font-semibold">Why it happens</h2>
      <p>{type.cause ?? NOT_SUMMARIZED}</p>
      <h2 className="mt-4 text-base font-semibold">How it was confirmed</h2>
      <p>{confirmedText(words, type)}</p>
      <h2 className="mt-4 text-base font-semibold">Every affected gene</h2>
      <FindingFilters
        view={view}
        words={words}
        state={state}
        onChange={go}
        errorFixed
      />
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
    </article>
  );
}
