"use client";

import { ComposerPrimitive, useAuiState } from "@assistant-ui/react";
import { Send, Square } from "lucide-react";
import { useRef } from "react";

import { ParamStepper } from "@/features/conversation/slash/ParamStepper";
import { SlashPopover } from "@/features/conversation/slash/SlashPopover";
import { commands } from "@/features/conversation/slash/registry";
import { useSlashCommands } from "@/features/conversation/slash/useSlashCommands";
import { getAuthHeaders } from "@/lib/api/http";
import {
  useConversationDetail,
  useConversationExists,
} from "@/state/useConversationExists";
import { useSessionStore } from "@/state/useSessionStore";

import {
  AttachButton,
  ComposerAttachmentList,
  useAttachmentRefusal,
} from "./ComposerAttachments";
import { PaymentBanners, useComposerBlock } from "./QuotaExhaustedBanner";
import {
  SIGN_IN_TO_BUILD,
  VeupathdbSignInRequired,
  useVeupathdbSignedIn,
} from "./VeupathdbSignInRequired";
import {
  formatTokens,
  formatCost,
  formatUsage,
} from "@/features/conversation/usageFormat";
import { threadUsage } from "@veupathdb/assistant-client";
import { useChatHelpers } from "@/features/conversation/runtime/chatHelpersContext";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const SEND_TO_STOP_GUARD_MS = 500;

/** True when a Stop click is the tail of a double-click on Send. */
export function stopClickBlocked(lastSendAt: number, now: number): boolean {
  return lastSendAt > 0 && now - lastSendAt < SEND_TO_STOP_GUARD_MS;
}

function ConversationUsageFooter() {
  const chat = useChatHelpers();
  const usage = threadUsage(chat.messages);
  if (usage.total.tokens === 0 && usage.total.costUsd === 0) return null;
  return (
    <div className="flex items-center gap-2 px-1 pt-1">
      <TooltipProvider delayDuration={150}>
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              data-testid="conversation-usage"
              tabIndex={0}
              className="cursor-help text-[11px] text-muted-foreground underline decoration-dotted underline-offset-2"
            >
              Conversation · {formatTokens(usage.total.tokens)} tokens ·{" "}
              {formatCost(usage.total.costUsd)}
            </span>
          </TooltipTrigger>
          <TooltipContent side="top" className="space-y-0.5 text-[11px]">
            <div className="text-muted-foreground">
              This conversation&apos;s total across all turns.
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">Assistant</span>
              <span className="font-mono tabular-nums">
                {formatUsage(usage.lead.tokens, usage.lead.costUsd)}
              </span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">Sub-agents</span>
              <span className="font-mono tabular-nums">
                {formatUsage(usage.subAgents.tokens, usage.subAgents.costUsd)}
              </span>
            </div>
            <div className="flex justify-between gap-4 border-t border-border/60 pt-0.5 font-medium">
              <span>Total</span>
              <span className="font-mono tabular-nums">
                {formatUsage(usage.total.tokens, usage.total.costUsd)}
              </span>
            </div>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  );
}

export function Composer({
  conversationId,
  assistantId,
}: {
  conversationId: string;
  assistantId: string;
}) {
  const siteId = useSessionStore((s) => s.selectedSite);
  const payment = useComposerBlock(conversationId);
  const signedIn = useVeupathdbSignedIn();
  const blocked = payment.blocked || !signedIn;
  const attachmentRefusal = useAttachmentRefusal();
  const isRunning = useAuiState((s) => s.thread.isRunning);
  const lastSendAt = useRef(0);
  const requestServerCancel = (): void => {
    void fetch(`/api/v1/conversations/${conversationId}/cancel`, {
      method: "POST",
      headers: getAuthHeaders(),
    }).catch(() => {});
  };
  const handleStopClick = (event: React.MouseEvent<HTMLButtonElement>): void => {
    if (stopClickBlocked(lastSendAt.current, Date.now())) {
      event.preventDefault();
      return;
    }
    requestServerCancel();
  };
  const { data: conversationDetail } = useConversationDetail(conversationId);
  const conversationExists = useConversationExists(conversationId);
  const slash = useSlashCommands({
    conversationId,
    siteId,
    stepCount: conversationDetail?.steps.length ?? 0,
    conversationExists,
  });

  return (
    <ComposerPrimitive.Root
      data-testid="message-composer"
      className="relative mx-auto flex w-full max-w-3xl flex-col gap-1 border-t bg-card px-4 pb-2 pt-3"
    >
      <SlashPopover
        open={slash.menuOpen}
        query={slash.query}
        commands={commands}
        ctx={slash.ctx}
        activeIdx={slash.activeIdx}
        onSelect={slash.select}
        onHover={slash.setActiveIdx}
      />
      <ParamStepper
        open={slash.pendingCommand !== null}
        command={slash.pendingCommand}
        onComplete={(values) => {
          if (slash.pendingCommand !== null) {
            void slash.run(slash.pendingCommand, values);
          }
        }}
        onCancel={slash.cancel}
      />
      <PaymentBanners conversationId={conversationId} />
      <VeupathdbSignInRequired />
      <div
        className="focus-within:shadow-[var(--shadow-composer-focus)] flex flex-col gap-2 rounded-lg border bg-background shadow-[var(--shadow-composer)] transition-shadow aria-disabled:opacity-60"
        aria-disabled={blocked}
      >
        <ComposerPrimitive.Input
          data-testid="message-input"
          placeholder={
            !signedIn
              ? SIGN_IN_TO_BUILD
              : (payment.placeholder ??
                "Ask about strategies, genes, or data... (try /help)")
          }
          className="max-h-36 w-full resize-none overflow-y-auto bg-transparent p-3 text-sm outline-none disabled:cursor-not-allowed"
          autoFocus
          disabled={blocked}
          onKeyDown={(event) => {
            if (
              attachmentRefusal !== null &&
              event.key === "Enter" &&
              !event.shiftKey
            ) {
              event.preventDefault();
              return;
            }
            slash.onKeyDown(event);
          }}
        />
        {slash.refusal !== null && (
          <p role="alert" className="px-3 text-xs text-destructive">
            {slash.refusal}
          </p>
        )}
        <ComposerAttachmentList assistantId={assistantId} refusal={attachmentRefusal} />
        <div className="flex items-center justify-between p-2">
          <AttachButton assistantId={assistantId} />
          {isRunning ? (
            <ComposerPrimitive.Cancel
              data-testid="stop-button"
              aria-label="Stop"
              onClick={handleStopClick}
              className="inline-flex items-center gap-2 rounded-md bg-destructive px-3 py-2 text-sm text-destructive-foreground shadow-[var(--shadow-card)] transition-transform hover:-translate-y-px"
            >
              <Square className="h-4 w-4" /> Stop
            </ComposerPrimitive.Cancel>
          ) : (
            <ComposerPrimitive.Send
              data-testid="send-button"
              aria-label="Send"
              disabled={blocked || attachmentRefusal !== null}
              onClick={(event) => {
                if (slash.refuseUnknown()) {
                  event.preventDefault();
                  return;
                }
                lastSendAt.current = Date.now();
              }}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground shadow-[var(--shadow-card)] transition-transform hover:-translate-y-px disabled:opacity-50 disabled:hover:translate-y-0"
            >
              <Send className="h-4 w-4" /> Send
            </ComposerPrimitive.Send>
          )}
        </div>
      </div>
      <ConversationUsageFooter />
    </ComposerPrimitive.Root>
  );
}
