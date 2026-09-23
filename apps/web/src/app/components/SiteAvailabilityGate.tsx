"use client";

import { SiteUnavailableNotice } from "@/features/sites/components/SiteUnavailableNotice";

/**
 * Replaces the routed content with the site notice while the shell reports the
 * site as down. The rail and the lists around it stay.
 */
export function SiteAvailabilityGate({
  siteId,
  down,
  children,
}: {
  siteId: string;
  down: boolean;
  children: React.ReactNode;
}) {
  if (!down) return <>{children}</>;

  return (
    <div className="flex h-full items-center justify-center bg-background px-6 py-10">
      <SiteUnavailableNotice siteId={siteId} />
    </div>
  );
}
