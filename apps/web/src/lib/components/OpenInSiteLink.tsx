"use client";

import { ExternalLink } from "lucide-react";
import { siteShortName } from "@pathfinder/shared";

import { Button } from "@/components/ui/button";
import { useSiteLinkTarget } from "@/lib/hooks/useSiteLinkTarget";

/** A link to a page on the site itself. */
export function OpenInSiteLink({ href, siteId }: { href: string; siteId: string }) {
  const target = useSiteLinkTarget();
  return (
    <Button asChild variant="ghost" size="sm" className="h-7 gap-1.5 px-2">
      <a href={href} target={target} rel="noreferrer">
        <span className="text-xs">{`Open in ${siteShortName(siteId)}`}</span>
        <ExternalLink className="size-3.5" aria-hidden />
      </a>
    </Button>
  );
}
