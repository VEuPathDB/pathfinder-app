"use client";

import type { UserQuestionAnswersPayload } from "@pathfinder/shared";
import type { UserQuestionAnswer } from "@pathfinder/shared/generated/types/UserQuestionAnswer";
import { getToolName, isToolUIPart, type UIMessage } from "ai";

import { useConsultAnswersStore } from "@/state/useConsultAnswersStore";

export interface ChatHelpersForApproval {
  addToolApprovalResponse: (response: {
    id: string;
    approved: boolean;
    reason?: string;
  }) => void;
}

export const USER_QUESTION_ANSWERS_PART_TYPE = "data-user-question-answers" as const;

/** The consult carousel answers this tool's approval with the user's answers. */
export const CONSULT_TOOL_NAME = "consult_user";

export function handleConsultSubmit(
  chat: ChatHelpersForApproval,
  pending: { approvalId: string },
  answers: UserQuestionAnswer[],
): void {
  useConsultAnswersStore.getState().recordAnswers(pending.approvalId, answers);
  chat.addToolApprovalResponse({ id: pending.approvalId, approved: true });
}

function answersPartsOf(part: UIMessage["parts"][number]): UIMessage["parts"] {
  if (!isToolUIPart(part) || getToolName(part) !== CONSULT_TOOL_NAME) return [part];
  if (part.state !== "approval-responded") return [part];
  const data: UserQuestionAnswersPayload = {
    toolCallId: part.toolCallId,
    answers: useConsultAnswersStore.getState().answersFor(part.approval.id),
  };
  return [part, { type: USER_QUESTION_ANSWERS_PART_TYPE, data }];
}

/** Each answered consult carries its answers to the turn that resumes it. */
export function withConsultAnswers(messages: UIMessage[]): UIMessage[] {
  return messages.map((message) => ({
    ...message,
    parts: message.parts.flatMap(answersPartsOf),
  }));
}
