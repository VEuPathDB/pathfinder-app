import type { UIMessage } from "ai";
import {
  buildTurnRequestBody,
  type TurnRequestBody,
} from "@veupathdb/assistant-client";

import type { PhaseModelMap, PhaseReasoningMap } from "@/state/useSettingsStore";

import { withConsultAnswers } from "../rail/consultActions";

export interface BuildChatRequestBodyArgs {
  conversationId: string;
  siteId: string;
  id: string;
  trigger: string;
  messages: UIMessage[];
  baseBody: Record<string, unknown> | undefined;
  phaseModels?: PhaseModelMap;
  phaseReasoning?: PhaseReasoningMap;
  /** Set only on the message that creates the thread: an existing thread
   *  keeps the assistant it was created with, and another id is refused. */
  assistantId?: string;
}

export type ChatRequestBodyShape = TurnRequestBody<UIMessage>;

/** The worker reads earlier turns from its checkpoint, so only the message
 *  being sent uploads its files. */
function withFilesOnLastOnly(messages: UIMessage[]): UIMessage[] {
  const last = messages.length - 1;
  return messages.map((message, index) =>
    index === last
      ? message
      : { ...message, parts: message.parts.filter((part) => part.type !== "file") },
  );
}

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
    messages: withFilesOnLastOnly(withConsultAnswers(args.messages)),
    baseBody: args.baseBody,
    extra: {
      siteId: args.siteId,
      assistantId: args.assistantId,
      phaseModels: args.phaseModels,
      phaseReasoning: args.phaseReasoning,
    },
  });
}
