"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { listAuditFindingsSuspenseQueryKey } from "@pathfinder/shared/generated/hooks/useListAuditFindingsSuspense";
import { startAuditRun } from "@pathfinder/shared/generated/hooks/useStartAuditRun";
import type { AuditRunView } from "@pathfinder/shared/generated/types/AuditRunView";

import { Button } from "@/components/ui/button";
import { toUserMessage } from "@/lib/api/errors";

import { auditRunOptions } from "./api";

type Action = NonNullable<AuditRunView["action"]>;

const LABELS: Record<Action, string> = {
  resume: "Resume the audit",
  retry: "Retry what was not read",
};

const HINTS: Record<Action, string> = {
  resume:
    "The audit goes on from the last unit it finished, with your VEuPathDB sign-in.",
  retry:
    "The audit reads again only the genomes, findings and evidence the site did not answer, refused for your sign-in, or the deadline left unread.",
};

export function RunAction({ view }: { view: AuditRunView }) {
  const queryClient = useQueryClient();
  const runId = view.run.id;
  const start = useMutation({
    mutationFn: (action: Action) =>
      startAuditRun(runId, { action }, { siteId: view.run.siteId }),
    onSuccess: (next) => {
      queryClient.setQueryData(auditRunOptions(runId).queryKey, next);
      void queryClient.invalidateQueries({
        queryKey: listAuditFindingsSuspenseQueryKey(runId),
      });
    },
    onError: (error) => {
      toast.error("The audit did not start", { description: toUserMessage(error) });
    },
  });
  const action = view.action;
  if (action === null) {
    return view.run.conversationId === null ? (
      <p className="my-3 text-xs text-muted-foreground">
        The conversation that started this audit was deleted, so it cannot start again.
      </p>
    ) : null;
  }
  return (
    <div className="my-3 flex items-center gap-3">
      <Button
        type="button"
        onClick={() => {
          start.mutate(action);
        }}
        disabled={start.isPending}
      >
        {start.isPending && (
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
        )}
        {LABELS[action]}
      </Button>
      <p className="text-xs text-muted-foreground">{HINTS[action]}</p>
    </div>
  );
}
