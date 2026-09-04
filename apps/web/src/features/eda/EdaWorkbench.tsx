"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import type { EdaAnalysisState } from "@pathfinder/shared";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { conversationEdaOptions, patchConversationEda } from "@/features/eda/api";
import { toUserMessage } from "@/lib/api/errors";
import { useEdaStore } from "@/state/eda";

import { ExportStepButton } from "./ExportStepButton";
import { StudyPicker } from "./StudyPicker";
import { ComputeCell } from "./cells/ComputeCell";
import { SubsetCell } from "./cells/SubsetCell";
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
  const bindingQuery = useQuery(options);
  const analysis = useEdaStore((s) => s.analysis);
  const applyAnalysisState = useEdaStore((s) => s.applyAnalysisState);

  const [hydrated, setHydrated] = useState<EdaAnalysisState | null>(null);
  const fetched = bindingQuery.data?.analysis ?? null;
  if (fetched !== null && hydrated !== fetched) {
    setHydrated(fetched);
    queueMicrotask(() => applyAnalysisState(fetched));
  }

  const [reported, setReported] = useState<unknown>(null);
  if (bindingQuery.error != null && reported !== bindingQuery.error) {
    setReported(bindingQuery.error);
    const message = toUserMessage(bindingQuery.error, READ_FAILED);
    queueMicrotask(() => toast.error(message));
  }

  const unbind = useMutation({
    mutationFn: () => patchConversationEda(conversationId, { action: "unbind" }),
    onSuccess: (response) => {
      queryClient.setQueryData(options.queryKey, {
        analysis: response.analysis,
        descriptor: null,
      });
      useEdaStore.getState().reset();
    },
    onError: (error) => {
      toast.error(toUserMessage(error, CLOSE_FAILED));
    },
  });

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header
        data-testid="eda-workbench-header"
        className="sticky top-0 z-10 flex h-11 shrink-0 items-center justify-between gap-3 border-b border-border bg-card px-4"
      >
        <WorkbenchTitle
          studyDisplayName={analysis?.studyDisplayName ?? ""}
          displayName={analysis?.displayName ?? ""}
          bound={analysis !== null}
        />
        {analysis !== null ? (
          <div className="flex shrink-0 items-center gap-2">
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
  isPending,
  error,
  onRetry,
  onUnbind,
  unbindPending,
}: {
  siteId: string;
  conversationId: string;
  analysisId: string | null;
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
  // Each cell holds local state about one analysis, so a switch remounts them.
  return (
    <div key={analysisId} className="flex flex-col gap-4">
      <SubsetCell siteId={siteId} conversationId={conversationId} />
      <ComputeCell siteId={siteId} conversationId={conversationId} />
      <VizCell siteId={siteId} conversationId={conversationId} />
    </div>
  );
}
