"use client";

import { useCurrentSite } from "@/app/hooks/useCurrentSite";
import { AuditRunsPage } from "@/features/audit/AuditRunsPage";

export default function Page() {
  const { siteId, isPortal } = useCurrentSite();
  return <AuditRunsPage onlySite={isPortal ? null : siteId} />;
}
