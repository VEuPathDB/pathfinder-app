import type { ConversationResponse } from "@pathfinder/shared/generated/types/ConversationResponse";

import { resolveAssistantId } from "@/lib/assistants";
import { provisionalName } from "@/lib/conversations/provisionalName";

export interface ConversationItem {
  id: string;
  title: string;
  updatedAt: string;
  siteId: string;
  assistantId: string;
  isDismissed: boolean;
  isSaved: boolean;
  stepCount: number;
  parentConversationId: string | null;
  parentMessageId: string | null;
  /** Full backend payload - kept so downstream handlers can inspect server state. */
  chat: ConversationResponse;
}

export function chatToConversationItem(
  chat: ConversationResponse,
  firstUserMessage: string | null,
): ConversationItem {
  return {
    id: chat.id,
    title: provisionalName(chat.name, firstUserMessage),
    updatedAt: chat.updatedAt,
    siteId: chat.siteId,
    assistantId: resolveAssistantId({ existing: chat.assistantId }),
    isDismissed: chat.dismissedAt != null,
    isSaved: chat.isSaved ?? false,
    stepCount: chat.stepCount ?? 0,
    parentConversationId: chat.parentConversationId ?? null,
    parentMessageId: chat.parentMessageId ?? null,
    chat,
  };
}
