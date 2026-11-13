import { queryOptions } from "@tanstack/react-query";
import { reduceSnapshot } from "@veupathdb/assistant-client";
import type { UIMessage } from "ai";
import { z } from "zod";
import { getShared } from "@strategist/shared/generated/hooks/useGetShared";
import { getSharedSnapshot } from "@strategist/shared/generated/hooks/useGetSharedSnapshot";

import { APIError } from "@/lib/api/http";

export const SHARED_POLL_MS = 4000;

export type SharedRefusal = "gone" | "locked" | "failed";

const lockedSchema = z.object({ code: z.literal("SHARE_LOCKED") });

export function passwordHeader(
  password: string | null,
): { "X-Share-Password": string } | undefined {
  return password === null ? undefined : { "X-Share-Password": password };
}

export function sharedRefusalOf(error: unknown): SharedRefusal {
  if (!(error instanceof APIError)) return "failed";
  if (error.status === 404) return "gone";
  if (lockedSchema.safeParse(error.data).success) return "locked";
  return "failed";
}

const RETRIES = 2;
const RETRY_DELAY_MS = 1000;

export function sharedRetry(failures: number, error: unknown): boolean {
  return failures < RETRIES && sharedRefusalOf(error) === "failed";
}

export function sharedPollAfter(error: unknown): number | false {
  return error === null || sharedRefusalOf(error) === "failed" ? SHARED_POLL_MS : false;
}

export function sharedHeadOptions(token: string, password: string | null) {
  return queryOptions({
    queryKey: ["shared", token, password] as const,
    queryFn: () => getShared(token, passwordHeader(password)),
    refetchInterval: (query) => sharedPollAfter(query.state.error),
    retry: sharedRetry,
    retryDelay: RETRY_DELAY_MS,
  });
}

export function sharedMessagesOptions(
  token: string,
  password: string | null,
  cursor: number,
) {
  return queryOptions({
    queryKey: ["shared", token, password, "snapshot", cursor] as const,
    queryFn: async (): Promise<{ cursor: number; messages: UIMessage[] }> => ({
      cursor,
      messages: reduceSnapshot(
        (await getSharedSnapshot(token, passwordHeader(password))).chunks,
      ),
    }),
    staleTime: Infinity,
    refetchInterval: (query) =>
      query.state.status === "error" ? SHARED_POLL_MS : false,
    retry: sharedRetry,
    retryDelay: RETRY_DELAY_MS,
  });
}
