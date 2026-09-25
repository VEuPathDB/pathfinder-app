"use client";

import { ThreadPrimitive, useAui, useAuiEvent } from "@assistant-ui/react";
import { useState } from "react";

import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import { chatUrl } from "@/lib/routes";
import { useSessionStore } from "@/state/useSessionStore";

import { ChatEmptyState } from "./ChatEmptyState";
import { Composer } from "./composer/Composer";
import {
  AssistantMessage,
  UserEditComposer,
  UserMessage,
} from "./content/MessageRenderer";

function ChatUrlSync({ conversationId }: { conversationId: string }) {
  const siteId = useSessionStore((s) => s.selectedSite);
  useAuiEvent("thread.runStart", () => {
    if (typeof window === "undefined") return;
    const target = chatUrl(siteId, conversationId);
    if (!window.location.pathname.startsWith(target)) {
      window.history.replaceState(null, "", target);
    }
  });
  return null;
}

export function ChatThread({
  conversationId,
  assistantId,
}: {
  conversationId: string;
  assistantId: string;
}) {
  const aui = useAui();
  const pendingSubmission = useSessionStore((s) => s.pendingUserSubmission);
  const [firedContent, setFiredContent] = useState<string | null>(null);
  if (
    pendingSubmission !== null &&
    pendingSubmission.conversationId === conversationId &&
    firedContent !== pendingSubmission.content
  ) {
    const content = pendingSubmission.content;
    setFiredContent(content);
    queueMicrotask(() => {
      useSessionStore.getState().setPendingUserSubmission(null);
      aui.thread().append(content);
    });
  }
  return (
    <>
      <ChatUrlSync conversationId={conversationId} />
      <ThreadPrimitive.Root className="flex h-full min-h-0 flex-col">
        <ThreadBody assistantId={assistantId} />
        <Composer conversationId={conversationId} assistantId={assistantId} />
      </ThreadPrimitive.Root>
    </>
  );
}

function ThreadBody({ assistantId }: { assistantId: string }) {
  return (
    <>
      <Conversation>
        <ConversationContent>
          <ChatEmptyState assistantId={assistantId} />
          <ThreadPrimitive.Messages
            components={{
              UserMessage,
              UserEditComposer,
              AssistantMessage,
            }}
          />
        </ConversationContent>
      </Conversation>
      <ConversationScrollButton />
    </>
  );
}
