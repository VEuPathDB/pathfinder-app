/**
 * Central URL builders. Site is now carried in the URL path, so every
 * navigation target needs a site id. Never inline
 * ``/${siteId}/conversation/...`` - always go through a helper here so the
 * path format stays in one place.
 */

import { DEFAULT_ASSISTANT_ID } from "@/lib/assistants";

/** The search param a draft chat route carries to name its assistant. */
export const ASSISTANT_PARAM = "assistant";

const CONVERSATION_ID_IN_PATH = /\/conversation\/([^/?#]+)/;

export function chatRoot(siteId: string, assistantId?: string): string {
  const base = `/${siteId}/conversation`;
  if (assistantId === undefined || assistantId === DEFAULT_ASSISTANT_ID) return base;
  return `${base}?${ASSISTANT_PARAM}=${encodeURIComponent(assistantId)}`;
}

/** The conversation the path names, or null on the draft route. */
export function conversationIdFromPath(pathname: string): string | null {
  return pathname.match(CONVERSATION_ID_IN_PATH)?.[1] ?? null;
}

export function chatUrl(siteId: string, conversationId: string): string {
  return `/${siteId}/conversation/${conversationId}`;
}

export function edaTabUrl(siteId: string, conversationId: string): string {
  return `/${siteId}/conversation/${conversationId}/eda`;
}

export function strategyCanvasUrl(siteId: string, conversationId: string): string {
  return `/${siteId}/conversation/${conversationId}/strategy`;
}

export function strategyStepUrl(
  siteId: string,
  conversationId: string,
  stepId: string,
): string {
  return `${strategyCanvasUrl(siteId, conversationId)}/step/${stepId}`;
}
