import { queryOptions } from "@tanstack/react-query";
import type { ControlSet } from "@pathfinder/shared";
import type { CreateControlSetRequest } from "@pathfinder/shared/generated/types/CreateControlSetRequest";
import { controlSetResponseSchema } from "@pathfinder/shared/generated/zod/controlSetResponseSchema";
import { z } from "zod";

import { requestJson } from "@/lib/api/http";

const ControlSetListSchema = z.array(controlSetResponseSchema);

export async function listControlSets(siteId: string): Promise<ControlSet[]> {
  return await requestJson(ControlSetListSchema, "/api/v1/control-sets", {
    query: { siteId },
  });
}

export function controlSetsOptions(siteId: string) {
  return queryOptions({
    queryKey: ["control-sets", "list", siteId] as const,
    queryFn: () => listControlSets(siteId),
    staleTime: 30_000,
    enabled: siteId !== "",
  });
}

export async function createControlSet(
  body: CreateControlSetRequest,
): Promise<ControlSet> {
  return await requestJson(controlSetResponseSchema, "/api/v1/control-sets", {
    method: "POST",
    body,
  });
}
