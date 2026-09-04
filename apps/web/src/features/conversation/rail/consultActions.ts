"use client";

import type { UserQuestionAnswersPayload } from "@pathfinder/shared";
import type { UserQuestionAnswer } from "@pathfinder/shared/generated/types/UserQuestionAnswer";
import type { UIMessage } from "ai";

export interface ChatHelpersForApproval {
  setMessages: (updater: (messages: UIMessage[]) => UIMessage[]) => void;
  addToolApprovalResponse: (response: {
    id: string;
    approved: boolean;
    reason?: string;
  }) => void;
}

export const USER_QUESTION_ANSWERS_PART_TYPE = "data-user-question-answers" as const;

export function handleConsultSubmit(
  chat: ChatHelpersForApproval,
  pending: { approvalId: string; sourceMessage: UIMessage },
  answers: UserQuestionAnswer[],
): void {
  const data: UserQuestionAnswersPayload = {
    toolCallId: pending.approvalId,
    answers,
  };
  const part: UIMessage["parts"][number] = {
    type: USER_QUESTION_ANSWERS_PART_TYPE,
    data,
  };

  chat.setMessages((messages) =>
    messages.map((msg) => {
      if (msg.id !== pending.sourceMessage.id) return msg;
      const filtered = msg.parts.filter(
        (p) => p.type !== USER_QUESTION_ANSWERS_PART_TYPE,
      );
      return { ...msg, parts: [...filtered, part] };
    }),
  );
  chat.addToolApprovalResponse({ id: pending.approvalId, approved: true });
}
