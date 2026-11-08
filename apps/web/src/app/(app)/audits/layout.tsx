"use client";

import { useCurrentSite } from "@/app/hooks/useCurrentSite";

export default function AuditsLayout({ children }: { children: React.ReactNode }) {
  const { offersAudits } = useCurrentSite();
  if (offersAudits) return children;
  return (
    <p
      role="status"
      className="m-6 rounded border border-dashed border-border p-10 text-center text-sm text-muted-foreground"
    >
      The gene model audit is not offered on this site.
    </p>
  );
}
