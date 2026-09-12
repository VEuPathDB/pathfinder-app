"use client";

import { usePathname, useSearchParams } from "next/navigation";

import { resolveAssistantId } from "@/lib/assistants";
import { ASSISTANT_PARAM, conversationIdFromPath } from "@/lib/routes";
import { useConversationDetail } from "@/state/useConversationExists";

/**
 * The assistant the reader is working with: the one the open thread was
 * created with, else the one the draft route names, else the default.
 */
export function useActiveAssistantId(): string {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { data } = useConversationDetail(conversationIdFromPath(pathname));
  return resolveAssistantId({
    existing: data?.assistantId,
    requested: searchParams.get(ASSISTANT_PARAM),
  });
}
