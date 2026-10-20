/**
 * Session state store - the site this tab works on, the site picked where the
 * website offers a picker, the two chat-remount signals and the conversation
 * this tab has created.
 *
 * Only the picked site persists; the rest is memory-only.
 */

import { createPersistedStore } from "./middleware";

interface SessionState {
  selectedSite: string;
  pickedSite: string;
  /** Text that the next-mounted ChatThread should auto-submit. */
  pendingUserSubmission: { conversationId: string; content: string } | null;
  /** Bumped to force a ChatThread remount after revert. */
  chatResetCounter: number;
  /** The conversation whose row this tab's first action created. */
  createdConversationId: string | null;

  setSelectedSite: (siteId: string) => void;
  setPickedSite: (siteId: string) => void;
  setPendingUserSubmission: (
    payload: { conversationId: string; content: string } | null,
  ) => void;
  bumpChatResetCounter: () => void;
  markConversationCreated: (conversationId: string) => void;
}

export const useSessionStore = createPersistedStore<SessionState>(
  "SessionStore",
  (set) => ({
    selectedSite: "veupathdb",
    pickedSite: "veupathdb",
    pendingUserSubmission: null,
    chatResetCounter: 0,
    createdConversationId: null,

    setSelectedSite: (siteId) =>
      set((s) => (s.selectedSite === siteId ? s : { selectedSite: siteId })),
    setPickedSite: (siteId) =>
      set((s) => (s.pickedSite === siteId ? s : { pickedSite: siteId })),
    setPendingUserSubmission: (payload) => set({ pendingUserSubmission: payload }),
    bumpChatResetCounter: () =>
      set((s) => ({ chatResetCounter: s.chatResetCounter + 1 })),
    markConversationCreated: (conversationId) =>
      set((s) =>
        s.createdConversationId === conversationId
          ? s
          : { createdConversationId: conversationId },
      ),
  }),
  {
    name: "pathfinder-session",
    partialize: (s) => ({ pickedSite: s.pickedSite }),
  },
);
