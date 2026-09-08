import type { UIMessage } from "ai";
import {
  DurableChatTransport,
  type DurableChatTransportOptions,
} from "@pathfinder/assistant-client/ai-sdk";

import { conversationCursors } from "../api/assistantClient";

/** A transport that resumes from the cursor the snapshot read also holds. */
export function createDurableTransport(
  options: Omit<DurableChatTransportOptions<UIMessage>, "cursors">,
): DurableChatTransport<UIMessage> {
  return new DurableChatTransport({ ...options, cursors: conversationCursors });
}
