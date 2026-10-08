import { queryOptions } from "@tanstack/react-query";
import { authStatusResponseSchema } from "@pathfinder/shared/generated/zod/authStatusResponseSchema";
import { authSuccessResponseSchema } from "@pathfinder/shared/generated/zod/authSuccessResponseSchema";

import { AppError } from "@/lib/errors/AppError";
import { invalidateUserScopedQueries } from "@/lib/query/invalidateUserScoped";
import { requestJson } from "./http";

// VEuPathDB auth bridge

const AUTH_STATUS_TIMEOUT_MS = 15_000;

function isTimeout(error: unknown): boolean {
  return error instanceof DOMException && error.name === "TimeoutError";
}

export async function getVeupathdbAuthStatus(
  siteId: string,
  signal?: AbortSignal,
): Promise<{ signedIn: boolean }> {
  const timeout = AbortSignal.timeout(AUTH_STATUS_TIMEOUT_MS);
  const raw = await requestJson(
    authStatusResponseSchema,
    `/api/v1/veupathdb/auth/status`,
    {
      query: { siteId },
      signal: signal === undefined ? timeout : AbortSignal.any([signal, timeout]),
    },
  ).catch((error: unknown) => {
    if (!isTimeout(error)) throw error;
    throw new AppError("The VEuPathDB sign-in check did not answer.", "TIMEOUT");
  });
  return { signedIn: raw.signedIn };
}

/**
 * Re-derive the internal ``pathfinder-auth`` token from a live VEuPathDB session.
 * Called on page load when the internal token is missing/expired.
 */
export async function refreshAuth(siteId: string): Promise<{ success: boolean }> {
  return await requestJson(
    authSuccessResponseSchema,
    `/api/v1/veupathdb/auth/refresh`,
    { method: "POST", query: { siteId } },
  );
}

function authRefreshKey(siteId: string) {
  return ["auth", "refresh", siteId] as const;
}

export function authStatusOptions(siteId: string) {
  return queryOptions({
    queryKey: ["auth", "status", siteId] as const,
    queryFn: async ({ client, signal }) => {
      const status = await getVeupathdbAuthStatus(siteId, signal);
      if (!status.signedIn) client.removeQueries({ queryKey: authRefreshKey(siteId) });
      return status;
    },
    enabled: siteId !== "",
  });
}

export function authRefreshOptions(siteId: string) {
  return queryOptions({
    queryKey: authRefreshKey(siteId),
    queryFn: async ({ client }) => {
      await refreshAuth(siteId);
      invalidateUserScopedQueries(client);
      return { refreshed: true };
    },
    staleTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
  });
}
