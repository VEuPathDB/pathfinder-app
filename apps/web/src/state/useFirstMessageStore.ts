/**
 * The first message a researcher sent in each thread this tab holds, keyed by
 * conversation. Memory-only: a conversation with no name yet shows it.
 */

import type { UIMessage } from "ai";

import { firstUserMessageText } from "@/lib/conversations/provisionalName";

import { createStore } from "./middleware";

interface FirstMessageState {
  byConversation: Record<string, string>;

  /** Record the thread's first user message. A recorded one is kept. */
  rememberFirstMessage: (
    conversationId: string,
    messages: readonly UIMessage[],
  ) => void;
}

export const useFirstMessageStore = createStore<FirstMessageState>(
  "FirstMessageStore",
  (set) => ({
    byConversation: {},

    rememberFirstMessage: (conversationId, messages) =>
      set((s) => {
        if (s.byConversation[conversationId] !== undefined) return s;
        const text = firstUserMessageText(messages);
        if (text === null) return s;
        return { byConversation: { ...s.byConversation, [conversationId]: text } };
      }),
  }),
);
