import type { ConsultQuestion } from "@pathfinder/shared/generated/types/ConsultQuestion";
import type { Proposal } from "@pathfinder/shared/generated/types/Proposal";
import type { UserQuestionAnswer } from "@pathfinder/shared/generated/types/UserQuestionAnswer";
import { consultQuestionSchema } from "@pathfinder/shared/generated/zod/consultQuestionSchema";
import { proposalSchema } from "@pathfinder/shared/generated/zod/proposalSchema";
import { userQuestionAnswerSchema } from "@pathfinder/shared/generated/zod/userQuestionAnswerSchema";
import { getToolName, isToolUIPart, type ToolUIPart, type UIMessage } from "ai";
import { z } from "zod";

import { PROPOSAL_TOOL_NAME } from "../../rail/consultActions";

export interface PendingConsult {
  approvalId: string;
  questions: ConsultQuestion[];
}

export interface ConsultRecap {
  questions: ConsultQuestion[];
  answers: UserQuestionAnswer[];
}

const toolInputSchema = z.object({ questions: z.array(z.unknown()) });

function questionsOf(input: unknown): ConsultQuestion[] {
  const parsed = toolInputSchema.safeParse(input);
  if (!parsed.success) return [];
  return parsed.data.questions.flatMap((raw) => {
    const question = consultQuestionSchema.safeParse(raw);
    return question.success ? [question.data] : [];
  });
}

function answersOf(output: unknown): UserQuestionAnswer[] {
  if (!Array.isArray(output)) return [];
  return output.flatMap((raw) => {
    const answer = userQuestionAnswerSchema.safeParse(raw);
    return answer.success ? [answer.data] : [];
  });
}

export function findConsultRecap(message: UIMessage): ConsultRecap | null {
  for (const part of message.parts) {
    if (
      part.type !== "tool-consult_user" ||
      !("state" in part) ||
      part.state !== "output-available"
    ) {
      continue;
    }
    return {
      questions: questionsOf("input" in part ? part.input : undefined),
      answers: answersOf("output" in part ? part.output : undefined),
    };
  }
  return null;
}

export function findPendingConsult(message: UIMessage): PendingConsult | null {
  for (const part of message.parts) {
    if (
      part.type === "tool-consult_user" &&
      "state" in part &&
      part.state === "approval-requested" &&
      "approval" in part
    ) {
      return {
        approvalId: part.approval.id,
        questions: questionsOf("input" in part ? part.input : undefined),
      };
    }
  }
  return null;
}

export type ProposalCardData = { proposal: Proposal } & (
  { decision: "pending"; approvalId: string } | { decision: "accepted" | "declined" }
);

function answeredDecision(
  state: ToolUIPart["state"],
  approved: boolean | undefined,
): "accepted" | "declined" | null {
  switch (state) {
    case "approval-responded":
      return approved === true ? "accepted" : "declined";
    case "output-available":
    case "output-error":
      return "accepted";
    case "output-denied":
      return "declined";
    case "input-streaming":
    case "input-available":
    case "approval-requested":
      return null;
  }
}

/** The proposal card this tool call carries, once its approval is asked. */
export function findProposal(
  message: UIMessage,
  toolCallId: string,
): ProposalCardData | null {
  for (const part of message.parts) {
    if (!isToolUIPart(part) || part.toolCallId !== toolCallId) continue;
    if (getToolName(part) !== PROPOSAL_TOOL_NAME) return null;
    const parsed = proposalSchema.safeParse(part.input);
    if (!parsed.success) return null;
    if (part.state === "approval-requested") {
      return {
        proposal: parsed.data,
        decision: "pending",
        approvalId: part.approval.id,
      };
    }
    const decision = answeredDecision(part.state, part.approval?.approved);
    return decision === null ? null : { proposal: parsed.data, decision };
  }
  return null;
}
