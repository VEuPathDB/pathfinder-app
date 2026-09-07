"use client";

import { useSuspenseQuery } from "@tanstack/react-query";

import { SiteUnavailableNotice } from "@/features/sites/components/SiteUnavailableNotice";
import { sitesOptions } from "@/lib/api/sites";
import { siteIsDown } from "@/lib/sites/availability";
import { QueryBoundary } from "@/lib/components/QueryBoundary";
import { AppShellError } from "./AppShellError";
import { LoadingScreen } from "./LoadingScreen";

/**
 * Keeps the app shell and its sign-in form off a site whose catalog the api
 * could not load. The sites query refetches on the api's retry interval, so a
 * site that becomes reachable again renders the app without a reload.
 */
export function SiteAvailabilityGate({
  siteId,
  children,
}: {
  siteId: string;
  children: React.ReactNode;
}) {
  return (
    <QueryBoundary loadingFallback={<LoadingScreen />} ErrorFallback={AppShellError}>
      <AvailableSiteOnly siteId={siteId}>{children}</AvailableSiteOnly>
    </QueryBoundary>
  );
}

function AvailableSiteOnly({
  siteId,
  children,
}: {
  siteId: string;
  children: React.ReactNode;
}) {
  const { data: sites } = useSuspenseQuery(sitesOptions());
  if (!siteIsDown(sites, siteId)) return <>{children}</>;

  return (
    <div className="flex h-full items-center justify-center bg-background px-6 py-10">
      <SiteUnavailableNotice siteId={siteId} />
    </div>
  );
}
