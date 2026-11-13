"use client";

import { ComposerPrimitive, useAuiState } from "@assistant-ui/react";
import { Send, Square } from "lucide-react";
import { useRef } from "react";

import { ParamStepper } from "@/features/conversation/slash/ParamStepper";
import { SlashPopover } from "@/features/conversation/slash/SlashPopover";
import { commands } from "@/features/conversation/slash/registry";
import { useSlashCommands } from "@/features/conversation/slash/useSlashCommands";
import { stopTurn } from "@/lib/api/conversations";
import { DEFAULT_ASSISTANT_ID } from "@/lib/assistants";
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
import { DockedCardView } from "./DockedCardView";
import { ModeSwitch } from "./ModeSwitch";
import { PaymentBanners, useComposerBlock } from "./QuotaExhaustedBanner";
import { useDockedCard } from "./useDockedCard";
import { SIGN_IN_TO_BUILD, useVeupathdbSignedIn } from "./useVeupathdbSignedIn";
import { SpendRing } from "./SpendRing";

const SEND_TO_STOP_GUARD_MS = 500;

/** True when a Stop click is the tail of a double-click on Send. */
export function stopClickBlocked(lastSendAt: number, now: number): boolean {
  return lastSendAt > 0 && now - lastSendAt < SEND_TO_STOP_GUARD_MS;
}

const DEFAULT_PLACEHOLDER = "Ask about strategies, genes, or data... (try /help)";
const ANSWER_PLACEHOLDER = "Or type your own answer";

const AI_NOTICE =
  "Strategist is an AI assistant and can make mistakes. Double-check important results.";

function ComposerFooter() {
  return (
    <div
      data-testid="composer-footer"
      className="flex flex-wrap items-center px-1 pt-1"
    >
      <p
        data-testid="ai-notice"
        className="min-w-64 flex-1 text-center text-xs text-muted-foreground"
      >
        {AI_NOTICE}
      </p>
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
  const docked = useDockedCard();
  const lastSendAt = useRef(0);
  const requestServerCancel = (): void => {
    stopTurn(conversationId);
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
      onSubmit={(event) => {
        if (docked.answerTyped()) event.preventDefault();
      }}
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
      <DockedCardView docked={docked} />
      <div
        className="focus-within:shadow-[var(--shadow-composer-focus)] flex flex-col gap-2 rounded-lg border bg-background shadow-[var(--shadow-composer)] transition-shadow aria-disabled:opacity-60"
        aria-disabled={blocked}
      >
        <ComposerPrimitive.Input
          data-testid="message-input"
          data-composer-input
          placeholder={
            !signedIn
              ? SIGN_IN_TO_BUILD
              : (payment.placeholder ??
                (docked.card === null ? DEFAULT_PLACEHOLDER : ANSWER_PLACEHOLDER))
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
        <div
          data-testid="composer-controls"
          className="flex flex-wrap items-center justify-between gap-2 p-2"
        >
          <div className="flex items-center gap-1">
            <AttachButton assistantId={assistantId} />
            <SpendRing />
          </div>
          <div className="flex items-center justify-end gap-2">
            {assistantId === DEFAULT_ASSISTANT_ID ? (
              <ModeSwitch conversationId={conversationId} />
            ) : null}
            {isRunning ? (
              <ComposerPrimitive.Cancel
                data-testid="stop-button"
                aria-label="Stop"
                onClick={handleStopClick}
                className="inline-flex items-center gap-2 rounded-md bg-destructive px-3 py-2 text-sm max-[900px]:min-h-11 text-destructive-foreground shadow-[var(--shadow-card)] transition-transform hover:-translate-y-px"
              >
                <Square className="h-4 w-4" /> Stop
              </ComposerPrimitive.Cancel>
            ) : (
              <ComposerPrimitive.Send
                data-testid="send-button"
                aria-label="Send"
                disabled={blocked || attachmentRefusal !== null}
                onClick={(event) => {
                  if (slash.refuseUnknown() || docked.answerTyped()) {
                    event.preventDefault();
                    return;
                  }
                  lastSendAt.current = Date.now();
                }}
                className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm max-[900px]:min-h-11 text-primary-foreground shadow-[var(--shadow-card)] transition-transform hover:-translate-y-px disabled:opacity-50 disabled:hover:translate-y-0"
              >
                <Send className="h-4 w-4" /> Send
              </ComposerPrimitive.Send>
            )}
          </div>
        </div>
      </div>
      <ComposerFooter />
    </ComposerPrimitive.Root>
  );
}
