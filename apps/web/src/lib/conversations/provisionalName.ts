import type { UIMessage } from "ai";

import { DEFAULT_STREAM_NAME } from "@pathfinder/shared";

const MAX_LENGTH = 60;

/** The first message cut to a word boundary, or null when it holds no text. */
function shortened(message: string): string | null {
  const text = message.replace(/\s+/g, " ").trim();
  if (text === "") return null;
  if (text.length <= MAX_LENGTH) return text;
  const head = text.slice(0, MAX_LENGTH + 1);
  const boundary = head.lastIndexOf(" ");
  const cut = boundary > 0 ? head.slice(0, boundary) : text.slice(0, MAX_LENGTH);
  return `${cut.trimEnd()}...`;
}

/**
 * The name a conversation shows. The generated title arrives at the end of the
 * first turn, so until then the first message stands in for it.
 */
export function provisionalName(name: string, firstUserMessage: string | null): string {
  if (name.trim() !== "") return name;
  const fromMessage = firstUserMessage === null ? null : shortened(firstUserMessage);
  return fromMessage ?? DEFAULT_STREAM_NAME;
}

/** The text of the first user message, or null when no user message has text. */
export function firstUserMessageText(messages: readonly UIMessage[]): string | null {
  const first = messages.find((message) => message.role === "user");
  if (first === undefined) return null;
  const text = first.parts
    .flatMap((part) => (part.type === "text" ? [part.text] : []))
    .join(" ")
    .trim();
  return text === "" ? null : text;
}
