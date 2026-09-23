"use client";

import { type UseQueryResult, useQuery, useSuspenseQuery } from "@tanstack/react-query";

import { siteUnavailableRefusal } from "@/lib/api/errors";
import { SITE_AVAILABILITY_INTERVAL_MS, sitesOptions } from "@/lib/api/sites";
import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { siteIsDown } from "@/lib/sites/availability";

export type SiteAccess =
  { kind: "pending" } | { kind: "down" } | { kind: "up"; signedIn: boolean };

/**
 * Whether the app shell can use a site: down when the site list reports it or
 * the sign-in status read is refused as SITE_UNAVAILABLE. Every other failure
 * of that read goes to the nearest error boundary.
 */
export function useSiteAccess(siteId: string): SiteAccess {
  const { data: sites } = useSuspenseQuery(sitesOptions());
  const status = useQuery({
    ...authStatusOptions(siteId),
    throwOnError: (error) => siteUnavailableRefusal(error) === null,
    refetchInterval: (query) =>
      siteUnavailableRefusal(query.state.error) === null
        ? false
        : SITE_AVAILABILITY_INTERVAL_MS,
  });

  if (siteIsDown(sites, siteId) || refusedLast(status)) return { kind: "down" };
  if (status.data === undefined) return { kind: "pending" };
  return { kind: "up", signedIn: status.data.signedIn };
}

/**
 * A new fetch clears the error of a status that holds no answer, and any other
 * error has already gone to the boundary, so an earlier error was a refusal.
 */
function refusedLast(status: UseQueryResult<unknown>): boolean {
  if (status.error !== null) return siteUnavailableRefusal(status.error) !== null;
  return status.data === undefined && status.errorUpdatedAt > 0;
}
