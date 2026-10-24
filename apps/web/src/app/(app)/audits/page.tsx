"use client";

import { useCurrentSite } from "@/app/hooks/useCurrentSite";
import { AuditRunsPage } from "@/features/audit/AuditRunsPage";

export default function Page() {
  const { locked } = useCurrentSite();
  return <AuditRunsPage lockedSite={locked?.id ?? null} />;
}
