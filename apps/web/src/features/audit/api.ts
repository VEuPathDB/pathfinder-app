import { queryOptions } from "@tanstack/react-query";
import {
  getAuditRunSuspense,
  getAuditRunSuspenseQueryOptions,
} from "@strategist/shared/generated/hooks/useGetAuditRunSuspense";
import { listAuditFindingsSuspenseQueryKey } from "@strategist/shared/generated/hooks/useListAuditFindingsSuspense";
import type { AuditRunView } from "@strategist/shared/generated/types/AuditRunView";

import { buildUrl } from "@/lib/api/http";

export const RUN_POLL_MS = 5_000;

export function isLiveRun(view: AuditRunView | undefined): boolean {
  const phase = view?.run.phase;
  return phase === "queued" || phase === "running" || view?.reviewsRunning === true;
}

export function runPollInterval(view: AuditRunView | undefined): number | false {
  return isLiveRun(view) ? RUN_POLL_MS : false;
}

export function auditRunOptions(runId: string) {
  const generated = getAuditRunSuspenseQueryOptions(runId);
  return queryOptions({
    ...generated,
    queryFn: async ({ client, signal }) => {
      const before = client.getQueryData(generated.queryKey);
      const next = await getAuditRunSuspense(runId, { signal });
      if (isLiveRun(before) && !isLiveRun(next)) {
        void client.invalidateQueries({
          queryKey: listAuditFindingsSuspenseQueryKey(runId),
        });
      }
      return next;
    },
    refetchInterval: (query) => runPollInterval(query.state.data),
  });
}

export function findingsCsvUrl(runId: string): string {
  return buildUrl(`/api/v1/audits/${runId}/findings.csv`);
}
