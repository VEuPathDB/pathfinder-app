import { queryOptions } from "@tanstack/react-query";
import { z } from "zod";

import { requestJson } from "./http";

const WebBuildSchema = z.object({ build: z.string() });

const CHECK_EVERY_MS = 5 * 60 * 1000;

export function servedWebBuildOptions(enabled: boolean) {
  return queryOptions({
    queryKey: ["web-build"] as const,
    queryFn: async () => (await requestJson(WebBuildSchema, "/api/v1/web-build")).build,
    enabled,
    staleTime: 0,
    retry: false,
    refetchInterval: CHECK_EVERY_MS,
    refetchOnWindowFocus: true,
  });
}
