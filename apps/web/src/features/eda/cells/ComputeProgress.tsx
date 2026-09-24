"use client";

import { useQuery } from "@tanstack/react-query";
import type { EdaDifferentialExpressionDescriptor } from "@pathfinder/shared/generated/types/EdaDifferentialExpressionDescriptor";

import { Button } from "@/components/ui/button";
import { patchConversationEda } from "@/features/eda/api";
import { toUserMessage } from "@/lib/api/errors";
import { isEdaJobRunning, useEdaStore, type EdaJobSnapshot } from "@/state/eda";

const POLL_INTERVAL_MS = 2_000;
const RUN_FAILED = "Could not run the compute";
const NO_JOB = "The run answered with no compute job.";

class ComputeJobMissingError extends Error {
  constructor() {
    super(NO_JOB);
    this.name = "ComputeJobMissingError";
  }
}

export interface ComputeProgressProps {
  conversationId: string;
  computation: EdaDifferentialExpressionDescriptor;
}

/** Repeating the identical run-compute action is the status poll: the job id
 * is a hash of the request. */
export function ComputeProgress({ conversationId, computation }: ComputeProgressProps) {
  const poll = useQuery({
    queryKey: ["eda", "compute", conversationId, computation] as const,
    queryFn: async (): Promise<EdaJobSnapshot> => {
      const response = await patchConversationEda(conversationId, {
        action: "run-compute",
        computation,
      });
      const job = response.job;
      if (job == null) throw new ComputeJobMissingError();
      const snapshot: EdaJobSnapshot = {
        jobId: job.jobId,
        taskId: job.taskId,
        appName: job.appName,
        status: job.status,
      };
      useEdaStore.getState().applyJob(snapshot);
      return snapshot;
    },
    refetchInterval: (query) => {
      if (query.state.status === "error") return false;
      const job = query.state.data;
      if (job === undefined) return POLL_INTERVAL_MS;
      return isEdaJobRunning(job) ? POLL_INTERVAL_MS : false;
    },
    retry: false,
    staleTime: 0,
    gcTime: 0,
    meta: { shownInline: true },
  });

  if (poll.error != null) {
    return (
      <p data-testid="eda-compute-error" className="text-xs text-destructive">
        {toUserMessage(poll.error, RUN_FAILED)}
      </p>
    );
  }

  const job = poll.data;
  if (job === undefined) return <RunningLine status="submitting" />;

  switch (job.status) {
    case "queued":
    case "in-progress":
      return <RunningLine status={job.status} />;
    case "complete":
      return (
        <p data-testid="eda-compute-complete" className="text-xs text-muted-foreground">
          Compute complete.
        </p>
      );
    case "failed":
      return (
        <p data-testid="eda-compute-failed" className="text-xs text-destructive">
          This compute failed and cannot be re-run. Change the configuration and run
          again.
        </p>
      );
    case "expired":
      return (
        <div data-testid="eda-compute-expired" className="flex items-center gap-2">
          <p className="text-xs text-muted-foreground">
            This compute expired. Run it again to recompute the same result.
          </p>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => void poll.refetch()}
          >
            Re-run compute
          </Button>
        </div>
      );
    case "no-such-job":
      return (
        <p data-testid="eda-compute-missing" className="text-xs text-muted-foreground">
          The service has no job for this configuration.
        </p>
      );
    default:
      return (
        <p
          data-testid="eda-compute-unknown-status"
          className="text-xs text-destructive"
        >
          {`The service answered with an unknown job status: ${job.status}.`}
        </p>
      );
  }
}

function RunningLine({ status }: { status: string }) {
  return (
    <div data-testid="eda-compute-progress" className="space-y-1">
      <div
        role="progressbar"
        aria-label="Compute progress"
        className="h-1 w-full overflow-hidden rounded bg-muted"
      >
        <div className="h-full w-1/3 animate-pulse rounded bg-primary" />
      </div>
      <p className="text-xs text-muted-foreground">{status}</p>
    </div>
  );
}
