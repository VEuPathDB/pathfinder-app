"use client";

import {
  AttachmentPrimitive,
  ComposerPrimitive,
  useAui,
  useAuiState,
} from "@assistant-ui/react";
import { useQuery } from "@tanstack/react-query";
import { FileText, Paperclip, Send, Square, X } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { ParamStepper } from "@/features/conversation/slash/ParamStepper";
import { SlashPopover } from "@/features/conversation/slash/SlashPopover";
import { commands, findCommand } from "@/features/conversation/slash/registry";
import type { Command, CommandResult } from "@/features/conversation/slash/types";
import { parseSlashInput } from "@/features/conversation/slash/parser";
import { beginStrategy } from "@pathfinder/shared/generated/hooks/useBeginStrategy";
import { toUserMessage } from "@/lib/api/errors";
import { getAuthHeaders } from "@/lib/api/http";
import { strategyQueryOptions } from "@/lib/api/strategy";
import { handleWdkAuthRefusal } from "@/state/useAuthGateStore";
import { useSessionStore } from "@/state/useSessionStore";

import { QuotaExhaustedBanner, useQuotaExhausted } from "./QuotaExhaustedBanner";
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

function GeneIdAttachmentChip() {
  return (
    <div className="flex items-center gap-1.5 rounded-md border border-border bg-muted/40 px-2 py-1 text-xs">
      <FileText className="size-3 shrink-0 text-muted-foreground" aria-hidden />
      <span className="max-w-[12rem] truncate">
        <AttachmentPrimitive.Name />
      </span>
      <AttachmentPrimitive.Remove
        aria-label="Remove attachment"
        className="ml-0.5 rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
      >
        <X className="size-3" />
      </AttachmentPrimitive.Remove>
    </div>
  );
}

export function Composer({ conversationId }: { conversationId: string }) {
  const aui = useAui();
  const text = useAuiState((s) => s.composer.text);
  const attachmentCount = useAuiState((s) => s.composer.attachments.length);
  const siteId = useSessionStore((s) => s.selectedSite);
  const quotaExhausted = useQuotaExhausted();
  const signedIn = useVeupathdbSignedIn();
  const blocked = quotaExhausted || !signedIn;
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
  const { data: conversationDetail } = useQuery(strategyQueryOptions(conversationId));
  const stepCount = conversationDetail?.steps.length ?? 0;

  const [pendingCommand, setPendingCommand] = useState<Command | null>(null);

  const parsed = parseSlashInput(text);
  const showPopover = pendingCommand === null && parsed !== null && parsed.rest === "";

  async function runCommand(command: Command, values: Record<string, string>) {
    const ctx = { conversationId, siteId, stepCount };

    try {
      await beginStrategy(conversationId, { siteId });
    } catch (err) {
      const retry = (): void => void runCommand(command, values);
      if (!handleWdkAuthRefusal(err, retry)) {
        toast.error(toUserMessage(err, "Failed to start conversation"));
      }
      return;
    }

    if (command.kind === "llm-prefill") {
      aui.composer().setText(command.prompt(values, ctx));
      if (command.autoSubmit === true) {
        aui.composer().send();
      }
      setPendingCommand(null);
      return;
    }

    try {
      const result: CommandResult = await command.run(values, ctx);
      aui.composer().setText("");
      setPendingCommand(null);
      handleResult(result);
    } catch (err) {
      aui.composer().setText("");
      setPendingCommand(null);
      const msg = err instanceof Error ? err.message : "Command failed";
      toast.error(msg);
    }
  }

  function handleResult(result: CommandResult) {
    if (result.kind === "toast") {
      if (result.type === "success") toast.success(result.message);
      else if (result.type === "error") toast.error(result.message);
      else toast.info(result.message);
      return;
    }
    if (result.kind === "download") {
      const a = document.createElement("a");
      a.href = result.url;
      a.download = result.filename;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      document.body.appendChild(a);
      a.click();
      a.remove();
      toast.success(`Downloading ${result.filename}`);
      return;
    }
    if (result.kind === "prefill") {
      aui.composer().setText(result.text);
      if (result.submit === true) aui.composer().send();
    }
  }

  function selectCommand(command: Command) {
    if (command.params.length === 0) {
      void runCommand(command, {});
      return;
    }
    setPendingCommand(command);
  }

  function dismissPopover() {
    aui.composer().setText("");
  }

  const exactMatch =
    parsed !== null && parsed.token !== "" ? findCommand(parsed.token) : null;
  const wantsDirectRun =
    exactMatch !== null &&
    exactMatch !== undefined &&
    parsed !== null &&
    parsed.rest === "";

  return (
    <ComposerPrimitive.Root
      data-testid="message-composer"
      className="relative mx-auto flex w-full max-w-3xl flex-col gap-1 border-t bg-card px-4 pb-2 pt-3"
    >
      <SlashPopover
        open={showPopover}
        query={parsed?.token ?? ""}
        commands={commands}
        ctx={{ conversationId, siteId, stepCount }}
        onSelect={selectCommand}
        onDismiss={dismissPopover}
      />
      <ParamStepper
        open={pendingCommand !== null}
        command={pendingCommand}
        ctx={{ conversationId, siteId, stepCount }}
        onComplete={(values) => {
          if (pendingCommand !== null) void runCommand(pendingCommand, values);
        }}
        onCancel={() => {
          setPendingCommand(null);
          aui.composer().setText("");
        }}
      />
      <QuotaExhaustedBanner />
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
              : quotaExhausted
                ? "Monthly quota reached - try again after the reset date."
                : "Ask about strategies, genes, or data... (try /help)"
          }
          className="max-h-36 w-full resize-none overflow-y-auto bg-transparent p-3 text-sm outline-none disabled:cursor-not-allowed"
          autoFocus
          disabled={blocked}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && wantsDirectRun) {
              e.preventDefault();
              selectCommand(exactMatch);
            }
          }}
        />
        {attachmentCount > 0 && (
          <div className="flex flex-wrap gap-1.5 px-2 pt-2">
            <ComposerPrimitive.Attachments>
              {() => <GeneIdAttachmentChip />}
            </ComposerPrimitive.Attachments>
          </div>
        )}
        <div className="flex items-center justify-between p-2">
          <ComposerPrimitive.AddAttachment
            data-testid="add-attachment"
            aria-label="Attach gene-ID file"
            className="inline-flex items-center gap-1.5 rounded-md border border-input px-2.5 py-2 text-xs text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground disabled:opacity-50"
          >
            <Paperclip className="h-4 w-4" /> Attach
          </ComposerPrimitive.AddAttachment>
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
              disabled={blocked}
              onClick={() => {
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
