/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";

import { useSessionStore } from "@/state/useSessionStore";

import { server } from "../../../../vitest.msw-setup";

import { beginConversation } from "./beginConversation";

const CONVERSATION_ID = "33333333-3333-4333-8333-333333333333";

beforeEach(() => {
  useSessionStore.setState({ createdConversationId: null });
});

describe("beginConversation", () => {
  it("records the conversation as one that now has a row", async () => {
    server.use(
      http.post(
        `http://localhost:3000/api/v1/conversations/${CONVERSATION_ID}/begin`,
        () =>
          HttpResponse.json({
            conversationId: CONVERSATION_ID,
            isNew: true,
            name: "strategy",
          }),
      ),
    );

    await beginConversation(CONVERSATION_ID, { siteId: "plasmodb" });

    expect(useSessionStore.getState().createdConversationId).toBe(CONVERSATION_ID);
  });
});
