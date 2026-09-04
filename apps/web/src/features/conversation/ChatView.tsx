"use client";

import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useQuery } from "@tanstack/react-query";
import type { UIMessage } from "ai";
import { redirect, useParams } from "next/navigation";
import { useState } from "react";
import { ErrorBoundary } from "react-error-boundary";

import type { Strategy } from "@pathfinder/shared";
import { strategyQueryOptions } from "@/lib/api/strategy";
import { conversationSnapshotOptions } from "@/features/conversation/api/conversationSnapshot";
import { chatRoot } from "@/lib/routes";
import { Spinner } from "@/components/ui/spinner";
import { useSessionStore } from "@/state/useSessionStore";

import { ChatThread } from "./ChatThread";
import { ChatViewError } from "./ChatViewError";
import { RightRail } from "./rail/RightRail";
import { ChatHelpersProvider } from "./runtime/chatHelpersContext";
import { useChatRuntime } from "./runtime/useChatRuntime";

export function ChatView({
  conversationId,
  allowMissing = false,
  resumable = false,
}: {
  conversationId: string;
  allowMissing?: boolean;
  resumable?: boolean;
}) {
  const params = useParams<{ siteId?: string }>();
  const siteSegment = params.siteId ?? "";
  const conversationsHref = chatRoot(siteSegment);
  const chatResetCounter = useSessionStore((s) => s.chatResetCounter);

  const detailQuery = useQuery(strategyQueryOptions(conversationId));
  const messagesQuery = useQuery({
    ...conversationSnapshotOptions(conversationId),
    enabled: allowMissing || detailQuery.data != null,
  });

  if (!allowMissing && detailQuery.isFetched && detailQuery.data === null) {
    redirect(conversationsHref);
  }

  if (detailQuery.isPending || messagesQuery.isPending) {
    return (
      <div className="flex h-full items-center justify-center bg-card">
        <Spinner className="size-5" />
      </div>
    );
  }

  const strategy = detailQuery.data ?? null;
  const siteId = strategy?.siteId ?? "";

  return (
    // A thread that cannot render leaves the rest of the app reachable.
    <ErrorBoundary
      resetKeys={[conversationId, chatResetCounter]}
      fallbackRender={({ error }) => (
        <ChatViewError error={error} conversationsHref={conversationsHref} />
      )}
    >
      <ChatViewBody
        key={`${conversationId}:${chatResetCounter}`}
        conversationId={conversationId}
        initialMessages={messagesQuery.data ?? []}
        resumable={resumable}
        strategy={strategy}
        siteId={siteId}
      />
    </ErrorBoundary>
  );
}

function ChatViewBody({
  conversationId,
  initialMessages,
  resumable,
  strategy,
  siteId,
}: {
  conversationId: string;
  initialMessages: UIMessage[];
  resumable: boolean;
  strategy: Strategy | null;
  siteId: string;
}) {
  // A turn this mount starts is already streaming into it. Only a turn that
  // was running before this mount is re-attached.
  const [resumeOnMount] = useState(resumable);
  const { runtime, chat } = useChatRuntime({
    conversationId,
    resume: resumeOnMount,
    initialMessages,
  });
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ChatHelpersProvider value={chat}>
        <div className="relative flex min-h-0 min-w-0 flex-1">
          <div className="relative flex min-h-0 min-w-0 flex-1 flex-col bg-card">
            <ChatThread conversationId={conversationId} />
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
