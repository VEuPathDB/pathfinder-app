import type { UIMessage } from "ai";

export interface WithdrawnPrompt {
  messages: UIMessage[];
  text: string | null;
}

export function withdrawPrompt(
  messages: UIMessage[],
  messageId: string,
): WithdrawnPrompt {
  const prompt = messages.find((message) => message.id === messageId);
  if (prompt === undefined) return { messages, text: null };
  const text = prompt.parts
    .flatMap((part) => (part.type === "text" ? [part.text] : []))
    .join(" ")
    .trim();
  return {
    messages: messages.filter((message) => message.id !== messageId),
    text: text === "" ? null : text,
  };
}

const TURN_WITHDRAWN = "data-turn-withdrawn";

export function reduceWithdrawnTurns(messages: UIMessage[]): UIMessage[] {
  if (
    !messages.some((message) =>
      message.parts.some((part) => part.type === TURN_WITHDRAWN),
    )
  ) {
    return messages;
  }
  return messages.map((message) => {
    const notice = message.parts.filter((part) => part.type === TURN_WITHDRAWN);
    return notice.length === 0 ? message : { ...message, parts: notice };
  });
}
