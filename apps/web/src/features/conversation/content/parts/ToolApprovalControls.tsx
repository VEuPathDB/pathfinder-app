"use client";

import { getToolName, isToolUIPart, type ToolUIPart, type UIMessage } from "ai";
import type { ReactElement } from "react";
import { toast } from "sonner";
import { deleteCascadePayloadSchema } from "@pathfinder/shared/generated/zod/deleteCascadePayloadSchema";
import { toolSummaryPayloadSchema } from "@pathfinder/shared/generated/zod/toolSummaryPayloadSchema";

import { recordProductEvent } from "@/lib/api/productEvents";
import {
  ApprovalCard,
  type ApprovalDecision,
} from "@/features/conversation/thread/ApprovalCard";
import {
  approvalPromptFor,
  approvalSubjectFor,
} from "@/features/conversation/toolNames";

import {
  ADOPTION_TOOL_NAME,
  CONSULT_TOOL_NAME,
  PROPOSAL_TOOL_NAME,
} from "../../rail/consultActions";
import { useChatHelpers } from "../../runtime/chatHelpersContext";
import { useThreadDevMode } from "../../thread/useThreadDevMode";
import { answeredInALaterMessage } from "./cardAnswers";

/** The tools whose approval their own card answers. */
const CARD_TOOLS: ReadonlySet<string> = new Set([
  CONSULT_TOOL_NAME,
  PROPOSAL_TOOL_NAME,
  ADOPTION_TOOL_NAME,
]);

export interface ToolApprovalView {
  approvalId: string;
  toolName: string;
  input: ToolUIPart["input"];
  decision: ApprovalDecision;
  /** The first line the thread holds for this call: the one written when it asked. */
  asked: string | null;
  /** Each other step the call removes, as the api named it when it asked. */
  removes: string[];
}

function decisionOf(
  state: ToolUIPart["state"],
  approved: boolean | undefined,
): ApprovalDecision {
  if (state === "approval-requested") return "pending";
  return approved === true ? "approved" : "denied";
}

function firstSummaryLine(messages: UIMessage[], toolCallId: string): string | null {
  for (const message of messages) {
    for (const part of message.parts) {
      if (part.type !== "data-tool-summary") continue;
      const parsed = toolSummaryPayloadSchema.safeParse(part.data);
      if (parsed.success && parsed.data.toolCallId === toolCallId) {
        return parsed.data.summary;
      }
    }
  }
  return null;
}

function removedSteps(messages: UIMessage[], toolCallId: string): string[] {
  for (const message of messages) {
    for (const part of message.parts) {
      if (part.type !== "data-delete-cascade") continue;
      const parsed = deleteCascadePayloadSchema.safeParse(part.data);
      if (parsed.success && parsed.data.toolCallId === toolCallId) {
        return parsed.data.removes;
      }
    }
  }
  return [];
}

/** The approval carried by one tool call, across every message in the thread. */
export function findToolApproval(
  messages: UIMessage[],
  toolCallId: string,
): ToolApprovalView | null {
  for (const message of messages) {
    for (const part of message.parts) {
      if (!isToolUIPart(part) || part.toolCallId !== toolCallId) continue;
      const approval = part.approval;
      if (approval === undefined) continue;
      return {
        approvalId: approval.id,
        toolName: getToolName(part),
        input: part.input,
        decision:
          part.state === "approval-requested" &&
          answeredInALaterMessage(messages, message.id)
            ? "answered"
            : decisionOf(part.state, approval.approved),
        asked: firstSummaryLine(messages, toolCallId),
        removes: removedSteps(messages, toolCallId),
      };
    }
  }
  return null;
}

export function ToolApprovalControls({
  toolCallId,
}: {
  toolCallId: string;
}): ReactElement | null {
  const chat = useChatHelpers();
  const { showRaw } = useThreadDevMode();
  const approval = findToolApproval(chat.messages, toolCallId);
  if (approval === null || CARD_TOOLS.has(approval.toolName)) return null;

  const respond = (approved: boolean) => {
    Promise.resolve(
      chat.addToolApprovalResponse({ id: approval.approvalId, approved }),
    ).catch(() => {
      toast.error("Approval could not be sent");
    });
    recordProductEvent({
      event: "card_answered",
      toolName: approval.toolName,
      approved,
      conversationId: chat.id,
    });
  };

  return (
    <ApprovalCard
      prompt={approvalPromptFor(approval.toolName, approval.asked)}
      input={approval.input}
      showRaw={showRaw}
      onApprove={() => respond(true)}
      onDeny={() => respond(false)}
      decision={approval.decision}
      subject={approvalSubjectFor(approval.toolName, approval.asked)}
      removes={approval.removes}
    />
  );
}
