import type { UIMessage } from "ai";

import { DEFAULT_STREAM_NAME } from "@pathfinder/shared";

/** The longest a first message stands in for the title, in code points. */
const MAX_LENGTH = 60;

/** The characters that separate words in a message. The api states the same set. */
const SPACES =
  /[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+/gu;

/** The first message cut to a word boundary, or null when it holds no text. */
function shortened(message: string): string | null {
  const text = message.replace(SPACES, " ").replace(/^ | $/g, "");
  if (text === "") return null;
  const chars = Array.from(text);
  if (chars.length <= MAX_LENGTH) return text;
  const head = chars.slice(0, MAX_LENGTH + 1);
  const boundary = head.lastIndexOf(" ");
  const cut = boundary > 0 ? head.slice(0, boundary) : chars.slice(0, MAX_LENGTH);
  return `${cut.join("")}...`;
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
