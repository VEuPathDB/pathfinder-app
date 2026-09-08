import type { UIMessage } from "ai";

import type { ChatHelpers } from "../../runtime/chatHelpersContext";

export type ThreadPart = UIMessage["parts"][number];

/** One data part of a thread, keyed by the kind the wire sends. */
export function threadPart(type: string, data: object): ThreadPart {
  return { type, data } as ThreadPart;
}

/** One assistant message carrying these parts. */
export function threadOf(parts: readonly ThreadPart[]): UIMessage[] {
  return [{ id: "m1", role: "assistant", parts: [...parts] }];
}

/** Chat helpers that read these messages and drive nothing else. */
export function chatHelpersFor(messages: UIMessage[]): ChatHelpers {
  return {
    id: "conv-1",
    messages,
    status: "ready",
    error: undefined,
    setMessages: () => {},
    sendMessage: async () => {},
    regenerate: async () => {},
    stop: async () => {},
    resumeStream: async () => {},
    addToolResult: async () => {},
    addToolOutput: async () => {},
    addToolApprovalResponse: () => {},
    clearError: () => {},
  };
}
