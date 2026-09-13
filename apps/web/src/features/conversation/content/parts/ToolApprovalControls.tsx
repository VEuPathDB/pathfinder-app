"use client";

import { getToolName, isToolUIPart, type ToolUIPart, type UIMessage } from "ai";
import type { ReactElement } from "react";
import { toast } from "sonner";

import {
  ApprovalCard,
  type ApprovalDecision,
} from "@/features/conversation/thread/ApprovalCard";
import { approvalPromptFor } from "@/features/conversation/toolNames";

import { CONSULT_TOOL_NAME } from "../../rail/consultActions";
import { useChatHelpers } from "../../runtime/chatHelpersContext";
import { useThreadDevMode } from "../../thread/useThreadDevMode";

export interface ToolApprovalView {
  approvalId: string;
  toolName: string;
  input: ToolUIPart["input"];
  decision: ApprovalDecision;
}

function decisionOf(
  state: ToolUIPart["state"],
  approved: boolean | undefined,
): ApprovalDecision {
  if (state === "approval-requested") return "pending";
  return approved === true ? "approved" : "denied";
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
        decision: decisionOf(part.state, approval.approved),
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
  if (approval === null || approval.toolName === CONSULT_TOOL_NAME) return null;

  const respond = (approved: boolean) => {
    Promise.resolve(
      chat.addToolApprovalResponse({ id: approval.approvalId, approved }),
    ).catch(() => {
      toast.error("Approval could not be sent");
    });
  };

  return (
    <ApprovalCard
      prompt={approvalPromptFor(approval.toolName)}
      input={approval.input}
      showRaw={showRaw}
      onApprove={() => respond(true)}
      onDeny={() => respond(false)}
      decision={approval.decision}
    />
  );
}
