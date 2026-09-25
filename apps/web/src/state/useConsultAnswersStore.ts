/**
 * The answers the consult carousel collected, keyed by the approval they
 * answer. Memory-only: the turn's request body reads them here.
 */

import type { UserQuestionAnswer } from "@pathfinder/shared/generated/types/UserQuestionAnswer";

import { createStore } from "./middleware";

interface ConsultAnswersState {
  byApprovalId: Record<string, UserQuestionAnswer[]>;

  recordAnswers: (approvalId: string, answers: UserQuestionAnswer[]) => void;
  /**
   * The recorded answers. A consult approval is answered only through the
   * carousel, which records first, so an unknown approval throws.
   */
  answersFor: (approvalId: string) => UserQuestionAnswer[];
}

export const useConsultAnswersStore = createStore<ConsultAnswersState>(
  "ConsultAnswersStore",
  (set, get) => ({
    byApprovalId: {},

    recordAnswers: (approvalId, answers) =>
      set((s) => ({ byApprovalId: { ...s.byApprovalId, [approvalId]: answers } })),

    answersFor: (approvalId) => {
      const answers = get().byApprovalId[approvalId];
      if (answers === undefined) {
        throw new Error(
          `No answers to your questions are recorded for approval ${approvalId}: ` +
            "the turn would resume with none and ask the same questions again.",
        );
      }
      return answers;
    },
  }),
);
