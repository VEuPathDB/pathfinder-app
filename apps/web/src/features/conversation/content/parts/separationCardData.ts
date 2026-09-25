import type { SeparationOffer } from "@pathfinder/shared";
import { separationReportSchema } from "@pathfinder/shared/generated/zod/separationReportSchema";
import { getToolName, isToolUIPart, type UIMessage } from "ai";
import { z } from "zod";

import { ADOPTION_TOOL_NAME } from "../../rail/consultActions";
import { answeredDecision } from "./consultData";

export type SeparationCardData = { offer: SeparationOffer } & (
  { decision: "pending"; approvalId: string } | { decision: "accepted" | "declined" }
);

const adoptionInputSchema = z.object({ task_id: z.string() });
const separationPartSchema = z.object({
  type: z.literal("data-separation-result"),
  data: separationReportSchema,
});

/** The offer a separation run reported under this task, in any message. */
function offerOf(messages: UIMessage[], taskId: string): SeparationOffer | null {
  for (const message of messages) {
    for (const part of message.parts) {
      const parsed = separationPartSchema.safeParse(part);
      if (parsed.success && parsed.data.data.taskId === taskId) {
        return parsed.data.data.offer ?? null;
      }
    }
  }
  return null;
}

/** The separation card this adoption call carries, once its approval is asked. */
export function findAdoption(
  messages: UIMessage[],
  messageId: string,
  toolCallId: string,
): SeparationCardData | null {
  const message = messages.find((m) => m.id === messageId);
  for (const part of message?.parts ?? []) {
    if (!isToolUIPart(part) || part.toolCallId !== toolCallId) continue;
    if (getToolName(part) !== ADOPTION_TOOL_NAME) return null;
    const input = adoptionInputSchema.safeParse(part.input);
    const offer = input.success ? offerOf(messages, input.data.task_id) : null;
    if (offer === null) return null;
    if (part.state === "approval-requested") {
      return { offer, decision: "pending", approvalId: part.approval.id };
    }
    const decision = answeredDecision(part.state, part.approval?.approved);
    return decision === null ? null : { offer, decision };
  }
  return null;
}
