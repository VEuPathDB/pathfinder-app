"use client";

import { useQuery } from "@tanstack/react-query";
import { siteShortName } from "@pathfinder/shared";
import { AlertTriangle } from "lucide-react";

import { sitesOptions } from "@/lib/api/sites";

/**
 * Says PathFinder cannot reach a site and repeats the reason the api gives for it.
 */
export function SiteUnavailableNotice({ siteId }: { siteId: string }) {
  const { data: sites } = useQuery(sitesOptions());
  const site = sites?.find((row) => row.id === siteId);
  const reason = site?.unavailableReason ?? null;

  return (
    <div
      role="alert"
      data-testid="site-unavailable-notice"
      className="mx-auto max-w-md rounded-lg border border-border bg-card px-6 py-5 text-center"
    >
      <AlertTriangle className="mx-auto h-7 w-7 text-amber-500" />
      <p className="mt-3 text-sm font-medium text-foreground">
        Couldn&apos;t reach {siteShortName(siteId)}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        {reason !== null
          ? `PathFinder cannot use this site right now: ${reason}. It keeps trying every minute, so this may clear on its own.`
          : "PathFinder cannot use this site right now. It keeps trying every minute, so this may clear on its own."}
      </p>
    </div>
  );
}
