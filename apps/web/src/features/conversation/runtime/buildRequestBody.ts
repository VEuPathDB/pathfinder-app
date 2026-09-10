import type { UIMessage } from "ai";
import {
  buildTurnRequestBody,
  type TurnRequestBody,
} from "@veupathdb/assistant-client";

import type { PhaseModelMap, PhaseReasoningMap } from "@/state/useSettingsStore";

export interface BuildChatRequestBodyArgs {
  conversationId: string;
  siteId: string;
  id: string;
  trigger: string;
  messages: UIMessage[];
  baseBody: Record<string, unknown> | undefined;
  phaseModels?: PhaseModelMap;
  phaseReasoning?: PhaseReasoningMap;
}

export type ChatRequestBodyShape = TurnRequestBody<UIMessage>;

export function buildChatRequestBody(
  args: BuildChatRequestBodyArgs,
): ChatRequestBodyShape {
  if (args.siteId.trim() === "") {
    throw new Error(
      "buildChatRequestBody: siteId is required but empty. " +
        "This means useSessionStore.selectedSite was not set before the chat " +
        "request was constructed.",
    );
  }
  return buildTurnRequestBody<UIMessage>({
    conversationId: args.conversationId,
    id: args.id,
    trigger: args.trigger,
    messages: args.messages,
    baseBody: args.baseBody,
    extra: {
      siteId: args.siteId,
      phaseModels: args.phaseModels,
      phaseReasoning: args.phaseReasoning,
    },
  });
}
