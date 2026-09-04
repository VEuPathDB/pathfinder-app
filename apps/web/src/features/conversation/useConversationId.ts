"use client";

import { usePathname } from "next/navigation";

const ROUTE_RE = /\/conversation\/([^/?#]+)/;

/** Current conversation id parsed from the `/conversation/:id` path segment,
 * with or without a leading `/:site` prefix. */
export function useConversationId(): string | null {
  const pathname = usePathname() as string | null;
  return pathname?.match(ROUTE_RE)?.[1] ?? null;
}
