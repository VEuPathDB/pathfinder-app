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

/** The proposal card answers this tool's approval with a yes or a no. */
export const PROPOSAL_TOOL_NAME = "propose_changes";

/** The separation card answers this tool's approval with a yes or a no. */
export const ADOPTION_TOOL_NAME = "adopt_separating_strategy";

/** The question id a yes on a proposal card is recorded under. */
const PROPOSAL_ANSWER_ID = "proposal";

export function handleConsultSubmit(
  chat: ChatHelpersForApproval,
  pending: { approvalId: string },
  answers: UserQuestionAnswer[],
): void {
  useConsultAnswersStore.getState().recordAnswers(pending.approvalId, answers);
  chat.addToolApprovalResponse({ id: pending.approvalId, approved: true });
}

/** Skipping declines the consult with no answers, the way a no declines a card. */
export function handleConsultSkip(
  chat: ChatHelpersForApproval,
  pending: { approvalId: string },
): void {
  chat.addToolApprovalResponse({ id: pending.approvalId, approved: false });
}

/**
 * A yes carries the note as the card's answer, the way a consult carries its
 * answers. A no carries the note as the denial's reason.
 */
export function handleProposalAnswer(
  chat: ChatHelpersForApproval,
  pending: { approvalId: string; question: string },
  answer: { accepted: boolean; note: string },
): void {
  const note = answer.note.trim();
  if (!answer.accepted) {
    chat.addToolApprovalResponse({
      id: pending.approvalId,
      approved: false,
      ...(note === "" ? {} : { reason: note }),
    });
    return;
  }
  handleConsultSubmit(chat, pending, [
    {
      questionId: PROPOSAL_ANSWER_ID,
      prompt: pending.question,
      chosenLabels: ["Yes"],
      note,
    },
  ]);
}

/**
 * A yes builds the measured strategy and needs no words, so it is a plain
 * approval. A no carries the note as the denial's reason.
 */
export function handleAdoptionAnswer(
  chat: ChatHelpersForApproval,
  approvalId: string,
  answer: { accepted: boolean; note: string },
): void {
  const note = answer.note.trim();
  chat.addToolApprovalResponse({
    id: approvalId,
    approved: answer.accepted,
    ...(answer.accepted || note === "" ? {} : { reason: note }),
  });
}

/** A consult and a proposal carry answers on a yes; a declined one carries none. */
function carriesAnswers(toolName: string, approved: boolean): boolean {
  if (!approved) return false;
  return toolName === CONSULT_TOOL_NAME || toolName === PROPOSAL_TOOL_NAME;
}

function answersPartsOf(part: UIMessage["parts"][number]): UIMessage["parts"] {
  if (!isToolUIPart(part) || part.state !== "approval-responded") return [part];
  if (!carriesAnswers(getToolName(part), part.approval.approved)) return [part];
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
