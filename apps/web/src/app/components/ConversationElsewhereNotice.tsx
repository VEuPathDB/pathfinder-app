"use client";

import { useSuspenseQuery } from "@tanstack/react-query";
import { siteShortName } from "@pathfinder/shared";

import { sitesOptions } from "@/lib/api/sites";
import { chatUrl } from "@/lib/routes";

export function ConversationElsewhereNotice({
  siteId,
  conversationId,
}: {
  siteId: string;
  conversationId: string;
}) {
  const { data: sites } = useSuspenseQuery(sitesOptions());
  const site = sites.find((s) => s.id === siteId);

  return (
    <div
      data-testid="conversation-elsewhere-notice"
      className="flex h-full items-center justify-center p-6"
    >
      <div className="max-w-md text-center text-sm text-muted-foreground">
        <p>This conversation is on {site?.displayName ?? siteShortName(siteId)}.</p>
        {site !== undefined && (
          <a
            href={`${site.pageUrl}${chatUrl(conversationId)}`}
            target="_top"
            className="mt-3 inline-block font-medium text-primary underline underline-offset-2"
          >
            Open it on {site.name}
          </a>
        )}
      </div>
    </div>
  );
}
