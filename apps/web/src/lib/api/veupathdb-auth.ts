import { queryOptions } from "@tanstack/react-query";
import type { LoginPayload } from "@pathfinder/shared/generated/types/LoginPayload";
import { authStatusResponseSchema } from "@pathfinder/shared/generated/zod/authStatusResponseSchema";
import { authSuccessResponseSchema } from "@pathfinder/shared/generated/zod/authSuccessResponseSchema";

import { AppError } from "@/lib/errors/AppError";
import { requestJson } from "./http";

// VEuPathDB auth bridge

const AUTH_STATUS_TIMEOUT_MS = 15_000;

function isTimeout(error: unknown): boolean {
  return error instanceof DOMException && error.name === "TimeoutError";
}

export async function getVeupathdbAuthStatus(siteId: string): Promise<{
  signedIn: boolean;
  name?: string | null;
  email?: string | null;
}> {
  const raw = await requestJson(
    authStatusResponseSchema,
    `/api/v1/veupathdb/auth/status`,
    { query: { siteId }, signal: AbortSignal.timeout(AUTH_STATUS_TIMEOUT_MS) },
  ).catch((error: unknown) => {
    if (!isTimeout(error)) throw error;
    throw new AppError("The VEuPathDB sign-in check did not answer.", "TIMEOUT");
  });
  return {
    signedIn: raw.signedIn,
    ...(raw.name !== undefined ? { name: raw.name } : {}),
    ...(raw.email !== undefined ? { email: raw.email } : {}),
  };
}

export async function loginVeupathdb(
  email: string,
  password: string,
  siteId: string,
): Promise<{ success: boolean }> {
  if (!email || !password) {
    throw new AppError("Email and password are required.", "INVARIANT_VIOLATION");
  }
  return await requestJson(authSuccessResponseSchema, `/api/v1/veupathdb/auth/login`, {
    method: "POST",
    query: { siteId },
    body: { email, password } satisfies LoginPayload,
  });
}

export async function logoutVeupathdb(siteId: string): Promise<{ success: boolean }> {
  return await requestJson(authSuccessResponseSchema, `/api/v1/veupathdb/auth/logout`, {
    method: "POST",
    query: { siteId },
  });
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

export function authStatusOptions(siteId: string) {
  return queryOptions({
    queryKey: ["auth", "status", siteId] as const,
    queryFn: () => getVeupathdbAuthStatus(siteId),
    enabled: siteId !== "",
  });
}

export function authRefreshOptions(siteId: string) {
  return queryOptions({
    queryKey: ["auth", "refresh", siteId] as const,
    queryFn: async () => {
      await refreshAuth(siteId);
      return { refreshed: true };
    },
    staleTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
  });
}
