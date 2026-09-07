"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";

import { sitesOptions } from "@/lib/api/sites";
import { chatRoot } from "@/lib/routes";

/**
 * Says a site does not answer, names the error class the api last saw, and
 * links every site that does answer.
 */
export function SiteUnavailableNotice({ siteId }: { siteId: string }) {
  const { data: sites } = useQuery(sitesOptions());
  const rows = sites ?? [];
  const site = rows.find((row) => row.id === siteId);
  const displayName = site?.displayName ?? siteId;
  const reason = site?.unavailableReason ?? null;
  const alternatives = rows.filter((row) => row.available);

  return (
    <div
      role="alert"
      data-testid="site-unavailable-notice"
      className="mx-auto max-w-md rounded-lg border border-border bg-card px-6 py-5 text-center"
    >
      <AlertTriangle className="mx-auto h-7 w-7 text-amber-500" />
      <p className="mt-3 text-sm font-medium text-foreground">
        {displayName} is not responding
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        {reason !== null
          ? `PathFinder cannot load its searches (${reason}). It retries every minute.`
          : "PathFinder cannot load its searches. It retries every minute."}
      </p>
      {alternatives.length > 0 && (
        <>
          <p className="mt-4 text-xs font-medium text-foreground">
            Open a database that answers:
          </p>
          <ul className="mt-2 space-y-1 text-xs">
            {alternatives.map((row) => (
              <li key={row.id}>
                <Link href={chatRoot(row.id)} className="text-primary hover:underline">
                  {row.displayName}
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
