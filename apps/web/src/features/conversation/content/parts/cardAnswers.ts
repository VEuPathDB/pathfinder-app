import type { UIMessage } from "ai";

export function answeredInALaterMessage(
  messages: readonly UIMessage[],
  messageId: string,
): boolean {
  const index = messages.findIndex((message) => message.id === messageId);
  return (
    index !== -1 && messages.slice(index + 1).some((message) => message.role === "user")
  );
}
