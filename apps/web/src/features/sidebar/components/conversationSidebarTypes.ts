import type { ConversationResponse } from "@pathfinder/shared/generated/types/ConversationResponse";

import { resolveAssistantId } from "@/lib/assistants";

export interface ConversationItem {
  id: string;
  title: string;
  updatedAt: string;
  siteId: string;
  assistantId: string;
  isDismissed: boolean;
  isSaved: boolean;
  stepCount: number;
  experimentId: string | null;
  parentConversationId: string | null;
  parentMessageId: string | null;
  /** Full backend payload — kept so downstream handlers can inspect server state. */
  chat: ConversationResponse;
}

export function chatToConversationItem(chat: ConversationResponse): ConversationItem {
  return {
    id: chat.id,
    title: chat.name.trim() === "" ? "New conversation" : chat.name,
    updatedAt: chat.updatedAt,
    siteId: chat.siteId,
    assistantId: resolveAssistantId({ existing: chat.assistantId }),
    isDismissed: chat.dismissedAt != null,
    isSaved: chat.isSaved ?? false,
    stepCount: chat.stepCount ?? 0,
    experimentId: chat.experimentId ?? null,
    parentConversationId: chat.parentConversationId ?? null,
    parentMessageId: chat.parentMessageId ?? null,
    chat,
  };
}
