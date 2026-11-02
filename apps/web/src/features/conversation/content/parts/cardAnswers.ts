import { getToolName, isToolUIPart, type UIMessage } from "ai";

export function answeredInALaterMessage(
  messages: readonly UIMessage[],
  messageId: string,
): boolean {
  const index = messages.findIndex((message) => message.id === messageId);
  return (
    index !== -1 && messages.slice(index + 1).some((message) => message.role === "user")
  );
}

export interface OpenCard {
  messageId: string;
  toolCallId: string;
  toolName: string;
  approvalId: string;
  input: unknown;
}

export function openCards(messages: readonly UIMessage[]): OpenCard[] {
  return messages.flatMap((message) =>
    answeredInALaterMessage(messages, message.id)
      ? []
      : message.parts.flatMap((part) =>
          isToolUIPart(part) && part.state === "approval-requested"
            ? [
                {
                  messageId: message.id,
                  toolCallId: part.toolCallId,
                  toolName: getToolName(part),
                  approvalId: part.approval.id,
                  input: part.input,
                },
              ]
            : [],
        ),
  );
}

export function isOpenCard(
  messages: readonly UIMessage[],
  toolCallId: string,
): boolean {
  return openCards(messages).some((card) => card.toolCallId === toolCallId);
}
