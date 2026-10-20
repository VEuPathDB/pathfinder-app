/**
 * Central URL builders. The site is never in the path: the website that frames
 * PathFinder decides it. Never inline ``/conversation/...``; always go through
 * a helper here so the path format stays in one place.
 */

/** The search param a draft chat route carries to name its assistant. */
export const ASSISTANT_PARAM = "assistant";

const CONVERSATION_ID_IN_PATH = /\/conversation\/([^/?#]+)/;

export function chatRoot(): string {
  return "/conversation";
}

/** The conversation the path names, or null on the draft route. */
export function conversationIdFromPath(pathname: string): string | null {
  return pathname.match(CONVERSATION_ID_IN_PATH)?.[1] ?? null;
}

export function chatUrl(conversationId: string): string {
  return `/conversation/${conversationId}`;
}

export function edaTabUrl(conversationId: string): string {
  return `/conversation/${conversationId}/eda`;
}

export function strategyCanvasUrl(conversationId: string): string {
  return `/conversation/${conversationId}/strategy`;
}

export function strategyStepUrl(conversationId: string, stepId: string): string {
  return `${strategyCanvasUrl(conversationId)}/step/${stepId}`;
}

export function helpUrl(): string {
  return "/help";
}

export type YourDataSection =
  | "sent"
  | "other-services"
  | "kept"
  | "deleting"
  | "learning"
  | "your-key"
  | "declined"
  | "contact";

export function yourDataUrl(section?: YourDataSection): string {
  const base = `${helpUrl()}/your-data`;
  return section === undefined ? base : `${base}#${section}`;
}
