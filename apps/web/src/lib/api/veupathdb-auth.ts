import { queryOptions } from "@tanstack/react-query";
import { authStatusResponseSchema } from "@pathfinder/shared/generated/zod/authStatusResponseSchema";

import { AppError } from "@/lib/errors/AppError";
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

export function authStatusOptions(siteId: string) {
  return queryOptions({
    queryKey: ["auth", "status", siteId] as const,
    queryFn: ({ signal }) => getVeupathdbAuthStatus(siteId, signal),
    enabled: siteId !== "",
  });
}
