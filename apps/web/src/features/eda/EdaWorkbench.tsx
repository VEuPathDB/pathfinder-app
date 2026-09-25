"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { toast } from "sonner";
import { siteShortName, type EdaAnalysisState } from "@pathfinder/shared";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { conversationEdaOptions, patchConversationEda } from "@/features/eda/api";
import { toUserMessage } from "@/lib/api/errors";
import { OpenInSiteLink } from "@/lib/components/OpenInSiteLink";
import { chatUrl } from "@/lib/routes";
import { useEdaStore } from "@/state/eda";

import { ExportStepButton } from "./ExportStepButton";
import { StudyPicker } from "./StudyPicker";
import { ComparisonSummary } from "./cells/ComparisonSummary";
import { SubsetSummary } from "./cells/SubsetSummary";
import { VizCell } from "./cells/VizCell";

const READ_FAILED = "Could not read the study";
const CLOSE_FAILED = "Could not close the analysis";

export interface EdaWorkbenchProps {
  siteId: string;
  conversationId: string;
}

export function EdaWorkbench({ siteId, conversationId }: EdaWorkbenchProps) {
  const queryClient = useQueryClient();
  const options = conversationEdaOptions(conversationId);
  const bindingQuery = useQuery({ ...options, meta: { shownInline: true } });
  const analysis = useEdaStore((s) => s.analysis);
  const applyAnalysisState = useEdaStore((s) => s.applyAnalysisState);

  const [hydrated, setHydrated] = useState<EdaAnalysisState | null>(null);
  const fetched = bindingQuery.data?.analysis ?? null;
  if (fetched !== null && hydrated !== fetched) {
    setHydrated(fetched);
    queueMicrotask(() => applyAnalysisState(fetched));
  }

  const unbind = useMutation({
    mutationFn: () => patchConversationEda(conversationId, { action: "unbind" }),
    onSuccess: (response) => {
      queryClient.setQueryData(options.queryKey, { analysis: response.analysis });
      useEdaStore.getState().reset();
    },
    onError: (error) => {
      toast.error(toUserMessage(error, CLOSE_FAILED));
    },
  });

  return (
    <div data-testid="eda-workbench" className="flex h-full min-h-0 flex-col">
      <header
        data-testid="eda-workbench-header"
        className="sticky top-0 z-10 flex h-11 shrink-0 items-center justify-between gap-3 border-b border-border bg-card px-4"
      >
        <div className="flex min-w-0 items-center gap-2">
          <Button asChild variant="ghost" size="sm" className="shrink-0 gap-1.5">
            <Link href={chatUrl(siteId, conversationId)}>
              <ArrowLeft className="size-4" aria-hidden />
              <span className="text-xs">Back to conversation</span>
            </Link>
          </Button>
          <div className="h-5 w-px shrink-0 bg-border" aria-hidden />
          <WorkbenchTitle
            studyDisplayName={analysis?.studyDisplayName ?? ""}
            displayName={analysis?.displayName ?? ""}
            bound={analysis !== null}
          />
        </div>
        {analysis !== null ? (
          <div className="flex min-w-0 items-center gap-2">
            {analysis.analysisUrl !== null ? (
              <>
                <span className="min-w-0 truncate text-xs text-muted-foreground">
                  {`Edit on ${siteShortName(analysis.siteId)}; this tab shows what the site holds.`}
                </span>
                <OpenInSiteLink href={analysis.analysisUrl} siteId={analysis.siteId} />
              </>
            ) : null}
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={unbind.isPending}
              onClick={() => unbind.mutate()}
            >
              Change study
            </Button>
            <ExportStepButton conversationId={conversationId} />
          </div>
        ) : null}
      </header>
      <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
        <WorkbenchBody
          siteId={siteId}
          conversationId={conversationId}
          analysisId={analysis?.analysisId ?? null}
          compared={analysis?.compute != null}
          isPending={bindingQuery.isPending}
          error={bindingQuery.error}
          onRetry={() => void bindingQuery.refetch()}
          onUnbind={() => unbind.mutate()}
          unbindPending={unbind.isPending}
        />
      </div>
    </div>
  );
}

function WorkbenchTitle({
  studyDisplayName,
  displayName,
  bound,
}: {
  studyDisplayName: string;
  displayName: string;
  bound: boolean;
}) {
  if (!bound) {
    return <span className="truncate text-sm font-medium">No study selected</span>;
  }
  return (
    <span className="flex min-w-0 items-baseline gap-2">
      <span data-testid="eda-workbench-title" className="truncate text-sm font-medium">
        {studyDisplayName}
      </span>
      {displayName !== "" && displayName !== studyDisplayName ? (
        <span
          data-testid="eda-workbench-subtitle"
          className="truncate text-xs text-muted-foreground"
        >
          {displayName}
        </span>
      ) : null}
    </span>
  );
}

function WorkbenchBody({
  siteId,
  conversationId,
  analysisId,
  compared,
  isPending,
  error,
  onRetry,
  onUnbind,
  unbindPending,
}: {
  siteId: string;
  conversationId: string;
  analysisId: string | null;
  compared: boolean;
  isPending: boolean;
  error: unknown;
  onRetry: () => void;
  onUnbind: () => void;
  unbindPending: boolean;
}) {
  if (error != null) {
    return (
      <div
        data-testid="eda-binding-error"
        className="rounded-md border border-border bg-card p-3 text-xs text-destructive"
      >
        <p>{toUserMessage(error, READ_FAILED)}</p>
        <div className="mt-2 flex items-center gap-2">
          <Button type="button" size="sm" variant="outline" onClick={onRetry}>
            Retry
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={unbindPending}
            onClick={onUnbind}
          >
            Open a different study
          </Button>
        </div>
      </div>
    );
  }
  if (isPending) {
    return (
      <div className="flex justify-center py-8">
        <Spinner className="size-5" />
      </div>
    );
  }
  if (analysisId === null) {
    return <StudyPicker siteId={siteId} conversationId={conversationId} />;
  }
  // A switch of analysis remounts the cells, so each reads its own analysis.
  return (
    <div key={analysisId} className="flex flex-col gap-4">
      <SubsetSummary />
      <ComparisonSummary />
      {compared ? <VizCell siteId={siteId} conversationId={conversationId} /> : null}
    </div>
  );
}
