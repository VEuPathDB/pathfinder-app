import type { UIMessage } from "ai";
import { afterEach, describe, expect, it } from "vitest";

import { useFirstMessageStore } from "./useFirstMessageStore";

function userMessage(id: string, text: string): UIMessage {
  return { id, role: "user", parts: [{ type: "text", text }] };
}

describe("useFirstMessageStore", () => {
  afterEach(() => useFirstMessageStore.setState({ byConversation: {} }));

  it("records the first user message of a thread and keeps it", () => {
    const { rememberFirstMessage } = useFirstMessageStore.getState();
    rememberFirstMessage("conv-1", [userMessage("u1", "find kinases")]);
    rememberFirstMessage("conv-1", [userMessage("u2", "something else")]);

    expect(useFirstMessageStore.getState().byConversation).toEqual({
      "conv-1": "find kinases",
    });
  });

  it("records nothing for a thread with no user text", () => {
    useFirstMessageStore.getState().rememberFirstMessage("conv-1", []);

    expect(useFirstMessageStore.getState().byConversation).toEqual({});
  });
});
