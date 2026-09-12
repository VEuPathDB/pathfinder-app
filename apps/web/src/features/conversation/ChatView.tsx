"use client";

import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useQuery } from "@tanstack/react-query";
import type { UIMessage } from "ai";
import { redirect, useParams } from "next/navigation";
import { useState } from "react";
import { ErrorBoundary } from "react-error-boundary";

import type { Strategy } from "@pathfinder/shared";
import { resolveAssistantId } from "@/lib/assistants";
import { conversationSnapshotOptions } from "@/features/conversation/api/conversationSnapshot";
import { chatRoot } from "@/lib/routes";
import { Spinner } from "@/components/ui/spinner";
import {
  useConversationDetail,
  useConversationExists,
} from "@/state/useConversationExists";

import { ChatThread } from "./ChatThread";
import { ChatViewError } from "./ChatViewError";
import { RightRail } from "./rail/RightRail";
import { ChatHelpersProvider } from "./runtime/chatHelpersContext";
import { useChatRuntime } from "./runtime/useChatRuntime";

export function ChatView({
  conversationId,
  resumable = false,
  requestedAssistantId = null,
}: {
  conversationId: string;
  resumable?: boolean;
  /** The assistant the URL names, honoured only by a thread that is new. */
  requestedAssistantId?: string | null;
}) {
  const params = useParams<{ siteId?: string }>();
  const siteSegment = params.siteId ?? "";
  const conversationsHref = chatRoot(siteSegment);

  const exists = useConversationExists(conversationId);
  // A thread with no row when this view opened renders from local state; it
  // waits for no read, and it is never sent back to the conversation list.
  const [mountedAsDraft] = useState(() => !exists);
  const detailQuery = useConversationDetail(conversationId);
  const messagesQuery = useQuery({
    ...conversationSnapshotOptions(conversationId),
    enabled: !mountedAsDraft && detailQuery.data != null,
  });

  if (!mountedAsDraft && detailQuery.isFetched && detailQuery.data === null) {
    redirect(conversationsHref);
  }

  if (!mountedAsDraft && (detailQuery.isPending || messagesQuery.isPending)) {
    return (
      <div className="flex h-full items-center justify-center bg-card">
        <Spinner className="size-5" />
      </div>
    );
  }

  const strategy = detailQuery.data ?? null;
  const siteId = strategy?.siteId ?? "";
  const assistantId = resolveAssistantId({
    existing: strategy?.assistantId,
    requested: requestedAssistantId,
  });

  return (
    // A thread that cannot render leaves the rest of the app reachable.
    <ErrorBoundary
      fallbackRender={({ error }) => (
        <ChatViewError error={error} conversationsHref={conversationsHref} />
      )}
    >
      <ChatViewBody
        conversationId={conversationId}
        initialMessages={messagesQuery.data?.messages ?? []}
        turnInFlight={messagesQuery.data?.turnInFlight ?? false}
        resumable={resumable}
        strategy={strategy}
        siteId={siteId}
        assistantId={assistantId}
      />
    </ErrorBoundary>
  );
}

function ChatViewBody({
  conversationId,
  initialMessages,
  turnInFlight,
  resumable,
  strategy,
  siteId,
  assistantId,
}: {
  conversationId: string;
  initialMessages: UIMessage[];
  turnInFlight: boolean;
  resumable: boolean;
  strategy: Strategy | null;
  siteId: string;
  assistantId: string;
}) {
  const { runtime, chat } = useChatRuntime({
    conversationId,
    resume: resumable,
    turnInFlight,
    initialMessages,
    assistantId,
  });
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ChatHelpersProvider value={chat}>
        <div className="relative flex min-h-0 min-w-0 flex-1">
          <div className="relative flex min-h-0 min-w-0 flex-1 flex-col bg-card">
            <ChatThread conversationId={conversationId} assistantId={assistantId} />
          </div>
          <RightRail
            conversationId={conversationId}
            strategy={strategy}
            siteId={siteId}
          />
        </div>
      </ChatHelpersProvider>
    </AssistantRuntimeProvider>
  );
}
