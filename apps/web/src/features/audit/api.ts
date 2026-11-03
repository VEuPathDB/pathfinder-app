import { queryOptions } from "@tanstack/react-query";
import { getAuditRunSuspenseQueryOptions } from "@pathfinder/shared/generated/hooks/useGetAuditRunSuspense";
import type { AuditRunView } from "@pathfinder/shared/generated/types/AuditRunView";

import { buildUrl } from "@/lib/api/http";

export const RUN_POLL_MS = 5_000;

export function runPollInterval(view: AuditRunView | undefined): number | false {
  const phase = view?.run.phase;
  return phase === "queued" || phase === "running" ? RUN_POLL_MS : false;
}

export function auditRunOptions(runId: string) {
  return queryOptions({
    ...getAuditRunSuspenseQueryOptions(runId),
    refetchInterval: (query) => runPollInterval(query.state.data),
  });
}

export function findingsCsvUrl(runId: string): string {
  return buildUrl(`/api/v1/audits/${runId}/findings.csv`);
}
