import type { ConsultQuestion } from "@pathfinder/shared/generated/types/ConsultQuestion";
import type { UserQuestionAnswer } from "@pathfinder/shared/generated/types/UserQuestionAnswer";
import { consultQuestionSchema } from "@pathfinder/shared/generated/zod/consultQuestionSchema";
import { userQuestionAnswerSchema } from "@pathfinder/shared/generated/zod/userQuestionAnswerSchema";
import type { UIMessage } from "ai";
import { z } from "zod";

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
