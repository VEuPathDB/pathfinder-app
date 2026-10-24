import { queryOptions } from "@tanstack/react-query";
import type { AuditWords } from "@pathfinder/shared/generated/types/AuditWords";
import { auditWordsSchema } from "@pathfinder/shared/generated/zod/auditWordsSchema";

import { requestJson } from "./http";

export async function getAuditWords(): Promise<AuditWords> {
  return await requestJson(auditWordsSchema, "/api/v1/audits/words");
}

export function auditWordsOptions() {
  return queryOptions({
    queryKey: ["audits", "words"] as const,
    queryFn: getAuditWords,
    staleTime: Infinity,
  });
}
