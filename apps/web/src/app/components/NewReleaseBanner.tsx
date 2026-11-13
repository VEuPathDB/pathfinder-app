"use client";

import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { servedWebBuildOptions } from "@/lib/api/webBuild";
import { aNewerBuildIsServed, currentWebBuild } from "@/lib/webBuild";
import { reloadPage } from "./reloadPage";

export function NewReleaseBanner() {
  const mine = currentWebBuild();
  const { data: served } = useQuery(servedWebBuildOptions(mine !== ""));

  if (served === undefined || !aNewerBuildIsServed({ mine, served })) return null;

  return (
    <div
      role="status"
      className="flex items-center justify-center gap-3 border-b border-border bg-muted px-4 py-2 text-xs text-muted-foreground"
    >
      <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
      <span>Strategist has been updated.</span>
      <Button
        size="sm"
        variant="outline"
        className="h-6 px-2 text-xs"
        onClick={reloadPage}
      >
        Reload
      </Button>
    </div>
  );
}
