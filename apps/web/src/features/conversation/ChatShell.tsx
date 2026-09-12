"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useState } from "react";

import { ASSISTANT_PARAM, conversationIdFromPath } from "@/lib/routes";

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
  allowMissing: boolean;
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
  const conversationId = chatIdFromUrl ?? generatedChatId;
  const allowMissing = conversationId === generatedChatId;
  // A conversation named in the URL can have a turn running in it. Whether
  // this tab generated the id says nothing about that.
  return { conversationId, allowMissing, resumable: chatIdFromUrl !== null };
}

/**
 * The draft a generated conversation id belongs to. The assistant is part of
 * it: two assistants on one path are two drafts, so the thread a first message
 * creates runs under the assistant the reader picked.
 */
export function draftRoute(
  pathname: string,
  requestedAssistantId: string | null,
): string {
  if (requestedAssistantId === null) return pathname;
  return `${pathname}?${ASSISTANT_PARAM}=${requestedAssistantId}`;
}

export function ChatShell() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const chatIdFromUrl = conversationIdFromPath(pathname);
  const requestedAssistantId = searchParams.get(ASSISTANT_PARAM);
  const currentDraft = draftRoute(pathname, requestedAssistantId);

  const [generatedChatId, setGeneratedChatId] = useState<string>(() =>
    crypto.randomUUID(),
  );
  const [lastSeenDraft, setLastSeenDraft] = useState<string>(currentDraft);

  if (chatIdFromUrl === null && lastSeenDraft !== currentDraft) {
    setLastSeenDraft(currentDraft);
    setGeneratedChatId(crypto.randomUUID());
  }

  // A route that owns the main pane renders its own page instead of the thread.
  if (isStrategyRoute(pathname) || isEdaRoute(pathname)) return null;

  const { conversationId, allowMissing, resumable } = computeChatResolution({
    pathname,
    generatedChatId,
  });

  return (
    <ChatView
      key={conversationId}
      conversationId={conversationId}
      allowMissing={allowMissing}
      resumable={resumable}
      requestedAssistantId={requestedAssistantId}
    />
  );
}
