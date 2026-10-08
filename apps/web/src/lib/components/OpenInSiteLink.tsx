"use client";

import { ExternalLink } from "lucide-react";
import { siteShortName } from "@pathfinder/shared";

import { Button } from "@/components/ui/button";

interface OpenInSiteLinkProps {
  href: string;
  siteId: string;
  onOpen?: () => void;
}

/** A link to a page on the site itself. */
export function OpenInSiteLink({ href, siteId, onOpen }: OpenInSiteLinkProps) {
  const label = `Open in ${siteShortName(siteId)}`;
  return (
    <Button asChild variant="ghost" size="sm" className="h-7 gap-1.5 px-2">
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        aria-label={label}
        onClick={onOpen}
      >
        <span className="text-xs">{label}</span>
        <ExternalLink className="size-3.5" aria-hidden />
      </a>
    </Button>
  );
}
