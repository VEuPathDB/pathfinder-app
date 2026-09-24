"use client";

import { useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { ChevronDown, ExternalLink } from "lucide-react";
import { siteShortName } from "@pathfinder/shared";
import {
  getStepRecords,
  getStepRecordsQueryKey,
} from "@pathfinder/shared/generated/hooks/useGetStepRecords";
import type { StepRecord } from "@pathfinder/shared/generated/types/StepRecord";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";
import { notOnSiteRefusal, toUserMessage } from "@/lib/api/errors";
import { cn } from "@/lib/utils/cn";

const PAGE_SIZE = 50;
const NOT_ON_SITE = "Not on the site yet";

interface StepResultsProps {
  conversationId: string;
  stepId: string;
  /** The step's id on the site; null until a push creates it. */
  wdkStepId: number | null | undefined;
  siteId: string;
  /** The count the footer shows. null = loading. -1 = unknown. */
  estimatedSize: number | null;
  hasUnsavedEdits: boolean;
}

function countLabel(count: number): string {
  return `${count.toLocaleString()} ${count === 1 ? "gene" : "genes"}`;
}

/** The genes a pushed step answers on its site, one page at a time. */
export function StepResults({
  conversationId,
  stepId,
  wdkStepId,
  siteId,
  estimatedSize,
  hasUnsavedEdits,
}: StepResultsProps) {
  const [open, setOpen] = useState(true);
  const pagingKey = `${stepId}:${wdkStepId ?? ""}`;
  const [paging, setPaging] = useState({ key: pagingKey, pages: 1 });
  const pageCount = paging.key === pagingKey ? paging.pages : 1;
  const pushed = wdkStepId != null;

  const pages = useQueries({
    queries: Array.from({ length: pageCount }, (_, index) => {
      const params = { siteId, offset: index * PAGE_SIZE, limit: PAGE_SIZE };
      return {
        queryKey: [
          ...getStepRecordsQueryKey(conversationId, stepId, params),
          { wdkStepId },
        ],
        queryFn: ({ signal }: { signal: AbortSignal }) =>
          getStepRecords(conversationId, stepId, params, { signal }),
        enabled: pushed,
        meta: { shownInline: true },
      };
    }),
  });

  const first = pages[0];
  const last = pages[pages.length - 1];
  const error = pages.find((p) => p.error !== null)?.error ?? null;
  const notOnSite = !pushed || notOnSiteRefusal(first?.error) !== null;
  const firstPending = first?.isPending === true && error === null;
  const records: StepRecord[] = pages.flatMap((p) => p.data?.records ?? []);
  const total = first?.data?.total ?? null;
  const stepUrl = first?.data?.stepUrl ?? null;
  const lastData = last?.data;
  const hasMore =
    lastData !== undefined &&
    lastData.records.length > 0 &&
    lastData.offset + lastData.records.length < lastData.total;
  const loadingMore = pageCount > 1 && last?.isPending === true && error === null;

  const headerCount = notOnSite
    ? NOT_ON_SITE
    : total !== null
      ? countLabel(total)
      : firstPending && estimatedSize !== null && estimatedSize >= 0
        ? countLabel(estimatedSize)
        : null;

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="mt-6 border-t border-border pt-4"
      data-testid="step-results"
    >
      <div className="flex items-center justify-between gap-2 text-xs">
        <CollapsibleTrigger className="inline-flex items-center gap-1.5 font-medium text-foreground">
          <ChevronDown
            className={cn("size-3.5 transition-transform", !open && "-rotate-90")}
            aria-hidden
          />
          Results
          {headerCount !== null && (
            <span className="font-normal text-muted-foreground">{headerCount}</span>
          )}
        </CollapsibleTrigger>
        {!notOnSite && stepUrl !== null && (
          <a
            href={stepUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-foreground hover:underline"
          >
            Open in {siteShortName(siteId)}
            <ExternalLink className="size-3" aria-hidden />
          </a>
        )}
      </div>
      {!notOnSite && (
        <CollapsibleContent className="mt-3 space-y-2">
          {hasUnsavedEdits && (
            <p className="text-xs text-muted-foreground">
              Results are for the saved step
            </p>
          )}
          {error !== null ? (
            <p className="text-xs text-destructive">{toUserMessage(error)}</p>
          ) : firstPending ? (
            <div className="space-y-1.5" data-testid="step-results-loading">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
            </div>
          ) : null}
          {records.length > 0 && <RecordList records={records} />}
          {hasMore && error === null && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="w-full"
              onClick={() => setPaging({ key: pagingKey, pages: pageCount + 1 })}
            >
              Show more
            </Button>
          )}
          {loadingMore && <Skeleton className="h-4 w-full" />}
        </CollapsibleContent>
      )}
    </Collapsible>
  );
}

function RecordList({ records }: { records: StepRecord[] }) {
  return (
    <ul className="divide-y divide-border text-xs">
      {records.map((record, position) => (
        <li
          key={`${position}:${record.geneId}`}
          className="flex flex-col gap-0.5 py-1.5"
          data-testid={`step-result-${record.geneId}`}
        >
          <div className="flex items-baseline gap-2">
            <a
              href={record.recordUrl}
              target="_blank"
              rel="noreferrer"
              className="font-mono text-foreground hover:underline"
            >
              {record.geneId}
            </a>
            {record.organism !== null && (
              <span className="truncate italic text-muted-foreground">
                {record.organism}
              </span>
            )}
          </div>
          {record.product !== null && (
            <span className="truncate text-muted-foreground" title={record.product}>
              {record.product}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
