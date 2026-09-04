"use client";

import { Check, ShieldAlert, X } from "lucide-react";
import type { ReactElement } from "react";

import { ToolInput } from "@/components/ai-elements/tool";
import { Button } from "@/components/ui/button";

export type ApprovalDecision = "pending" | "approved" | "denied";

export interface ApprovalCardProps {
  prompt: string;
  input: unknown;
  showRaw: boolean;
  onApprove: () => void;
  onDeny: () => void;
  decision: ApprovalDecision;
}

function Decision({ approved }: { approved: boolean }): ReactElement {
  return (
    <div
      data-testid="tool-approval-decision"
      className={`flex items-center gap-1.5 py-1 text-xs ${
        approved ? "text-success" : "text-destructive"
      }`}
    >
      {approved ? (
        <Check className="size-3.5" aria-hidden />
      ) : (
        <X className="size-3.5" aria-hidden />
      )}
      {approved ? "Approved" : "Denied"}
    </div>
  );
}

/** The one bordered box the thread still draws, because the user must act. */
export function ApprovalCard({
  prompt,
  input,
  showRaw,
  onApprove,
  onDeny,
  decision,
}: ApprovalCardProps): ReactElement {
  if (decision !== "pending") return <Decision approved={decision === "approved"} />;
  return (
    <div
      data-testid="approval-card"
      className="mt-3 space-y-2 rounded-md border border-warning/40 bg-warning/10 p-3"
    >
      <p
        data-testid="approval-card-title"
        className="flex items-center gap-1.5 text-xs font-medium"
      >
        <ShieldAlert className="size-3.5 text-warning" aria-hidden />
        {prompt}
      </p>
      {showRaw && <ToolInput input={input} className="p-0" />}
      <div data-testid="tool-approval-controls" className="flex justify-end gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={onDeny}
          data-testid="tool-approval-deny"
        >
          <X className="mr-1 size-3.5" aria-hidden /> Deny
        </Button>
        <Button
          type="button"
          size="sm"
          onClick={onApprove}
          data-testid="tool-approval-approve"
        >
          <Check className="mr-1 size-3.5" aria-hidden /> Approve
        </Button>
      </div>
    </div>
  );
}
