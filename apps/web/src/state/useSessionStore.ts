/**
 * Session state store - selected site plus the two chat-remount signals.
 *
 * Only the site selection persists; the signals are memory-only.
 */

import { createPersistedStore } from "./middleware";

interface SessionState {
  selectedSite: string;
  /** Text that the next-mounted ChatThread should auto-submit. */
  pendingUserSubmission: { conversationId: string; content: string } | null;
  /** Bumped to force a ChatThread remount after revert. */
  chatResetCounter: number;

  setSelectedSite: (siteId: string) => void;
  setPendingUserSubmission: (
    payload: { conversationId: string; content: string } | null,
  ) => void;
  bumpChatResetCounter: () => void;
}

export const useSessionStore = createPersistedStore<SessionState>(
  "SessionStore",
  (set) => ({
    selectedSite: "veupathdb",
    pendingUserSubmission: null,
    chatResetCounter: 0,

    setSelectedSite: (siteId) =>
      set((s) => (s.selectedSite === siteId ? s : { selectedSite: siteId })),
    setPendingUserSubmission: (payload) => set({ pendingUserSubmission: payload }),
    bumpChatResetCounter: () =>
      set((s) => ({ chatResetCounter: s.chatResetCounter + 1 })),
  }),
  {
    name: "pathfinder-session",
    partialize: (s) => ({ selectedSite: s.selectedSite }),
  },
);
