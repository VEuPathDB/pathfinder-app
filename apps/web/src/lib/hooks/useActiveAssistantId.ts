"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname, useSearchParams } from "next/navigation";

import { strategyQueryOptions } from "@/lib/api/strategy";
import { resolveAssistantId } from "@/lib/assistants";
import { ASSISTANT_PARAM, conversationIdFromPath } from "@/lib/routes";

/**
 * The assistant the reader is working with: the one the open thread was
 * created with, else the one the draft route names, else the default.
 */
export function useActiveAssistantId(): string {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const conversationId = conversationIdFromPath(pathname);
  const { data } = useQuery({
    ...strategyQueryOptions(conversationId ?? ""),
    enabled: conversationId !== null,
  });
  return resolveAssistantId({
    existing: data?.assistantId,
    requested: searchParams.get(ASSISTANT_PARAM),
  });
}
