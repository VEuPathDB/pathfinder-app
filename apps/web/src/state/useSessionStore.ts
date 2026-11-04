/**
 * Session state store - the site this tab works on, the two chat-remount
 * signals and the conversation this tab has created. All of it is memory-only.
 */

import { createStore } from "./middleware";

interface SessionState {
  selectedSite: string;
  /** Text that the next-mounted ChatThread should auto-submit. */
  pendingUserSubmission: { conversationId: string; content: string } | null;
  /** Bumped to force a ChatThread remount after revert. */
  chatResetCounter: number;
  /** The conversation whose row this tab's first action created. */
  createdConversationId: string | null;

  setSelectedSite: (siteId: string) => void;
  setPendingUserSubmission: (
    payload: { conversationId: string; content: string } | null,
  ) => void;
  bumpChatResetCounter: () => void;
  markConversationCreated: (conversationId: string) => void;
}

export const useSessionStore = createStore<SessionState>("SessionStore", (set) => ({
  selectedSite: "veupathdb",
  pendingUserSubmission: null,
  chatResetCounter: 0,
  createdConversationId: null,

  setSelectedSite: (siteId) =>
    set((s) => (s.selectedSite === siteId ? s : { selectedSite: siteId })),
  setPendingUserSubmission: (payload) => set({ pendingUserSubmission: payload }),
  bumpChatResetCounter: () =>
    set((s) => ({ chatResetCounter: s.chatResetCounter + 1 })),
  markConversationCreated: (conversationId) =>
    set((s) =>
      s.createdConversationId === conversationId
        ? s
        : { createdConversationId: conversationId },
    ),
}));
