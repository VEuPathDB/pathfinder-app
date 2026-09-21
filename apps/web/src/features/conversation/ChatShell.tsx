"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useState } from "react";

import { ASSISTANT_PARAM, conversationIdFromPath } from "@/lib/routes";
import { useSessionStore } from "@/state/useSessionStore";

import { ChatView } from "./ChatView";

const STRATEGY_PATH = /\/conversation\/[^/]+\/strategy(\/|$)/;
const EDA_PATH = /\/conversation\/[^/]+\/eda(\/|$)/;

export function isStrategyRoute(pathname: string): boolean {
  return STRATEGY_PATH.test(pathname);
}

export function isEdaRoute(pathname: string): boolean {
  return EDA_PATH.test(pathname);
}

export interface ChatResolution {
  conversationId: string;
  resumable: boolean;
}

export function computeChatResolution({
  pathname,
  generatedChatId,
}: {
  pathname: string;
  generatedChatId: string;
}): ChatResolution {
  const chatIdFromUrl = conversationIdFromPath(pathname);
  // A conversation named in the URL can have a turn running in it. Whether
  // this tab generated the id says nothing about that.
  return {
    conversationId: chatIdFromUrl ?? generatedChatId,
    resumable: chatIdFromUrl !== null,
  };
}

/**
 * The route a conversation id belongs to. The assistant is part of it: two
 * assistants on one path are two drafts, so the thread a first message creates
 * runs under the assistant the reader picked.
 */
export function routeKey(
  pathname: string,
  requestedAssistantId: string | null,
): string {
  if (requestedAssistantId === null) return pathname;
  return `${pathname}?${ASSISTANT_PARAM}=${requestedAssistantId}`;
}

/**
 * True when the URL now names no conversation and the route moved. A draft id
 * belongs to one visit of the draft route, so every arrival there is a new
 * thread.
 */
export function needsNewDraftId(currentRoute: string, lastSeenRoute: string): boolean {
  if (conversationIdFromPath(currentRoute) !== null) return false;
  return currentRoute !== lastSeenRoute;
}

export function ChatShell() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const chatResetCounter = useSessionStore((s) => s.chatResetCounter);
  const requestedAssistantId = searchParams.get(ASSISTANT_PARAM);
  const currentRoute = routeKey(pathname, requestedAssistantId);

  const [generatedChatId, setGeneratedChatId] = useState<string>(() =>
    crypto.randomUUID(),
  );
  const [lastSeenRoute, setLastSeenRoute] = useState<string>(currentRoute);

  if (needsNewDraftId(currentRoute, lastSeenRoute)) {
    setGeneratedChatId(crypto.randomUUID());
  }
  if (lastSeenRoute !== currentRoute) {
    setLastSeenRoute(currentRoute);
  }

  const { conversationId, resumable } = computeChatResolution({
    pathname,
    generatedChatId,
  });

  // A route that owns the main pane takes the whole pane, so the thread is
  // hidden and costs no layout. It stays mounted: the composer text and a
  // running turn belong to the thread and outlive a visit to that route.
  const covered = isStrategyRoute(pathname) || isEdaRoute(pathname);

  return (
    <div
      data-testid="chat-pane"
      hidden={covered}
      className={covered ? undefined : "flex min-h-0 min-w-0 flex-1"}
    >
      {/* A revert opens the thread again, on a conversation that now has a row. */}
      <ChatView
        key={`${conversationId}:${chatResetCounter}`}
        conversationId={conversationId}
        resumable={resumable}
        requestedAssistantId={requestedAssistantId}
      />
    </div>
  );
}
