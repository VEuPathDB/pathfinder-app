"use client";

import { Download } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";

import { findingsCsvUrl } from "./api";

export function DownloadFindings({ runId, total }: { runId: string; total: number }) {
  if (total === 0) return null;
  return (
    <a
      href={findingsCsvUrl(runId)}
      download
      aria-label={`Download the ${String(total)} findings of this audit as a spreadsheet (CSV)`}
      className={buttonVariants({ variant: "outline", size: "sm" })}
    >
      <Download className="h-3.5 w-3.5" aria-hidden />
      Download findings (CSV)
    </a>
  );
}
