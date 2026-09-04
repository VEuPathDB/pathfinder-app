"use client";

import { createContext, useContext } from "react";
import type { useChat } from "@ai-sdk/react";
import type { UIMessage } from "ai";

export type ChatHelpers = ReturnType<typeof useChat<UIMessage>>;

const ChatHelpersContext = createContext<ChatHelpers | null>(null);

export const ChatHelpersProvider = ChatHelpersContext.Provider;

export function useChatHelpers(): ChatHelpers {
  const helpers = useContext(ChatHelpersContext);
  if (helpers === null) {
    throw new Error(
      "useChatHelpers must be used inside a ChatHelpersProvider — wrap with the chat runtime",
    );
  }
  return helpers;
}
