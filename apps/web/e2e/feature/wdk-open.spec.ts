import type {
  ConversationResponse,
  OpenConversationResponse,
} from "@pathfinder/shared";

import { test, expect } from "../fixtures/test";

/** The open route makes a conversation on the site it names. */
test.describe("Open conversation", () => {
  test("POST /open with a siteId creates a retrievable conversation", async ({
    apiClient,
    siteId,
  }) => {
    const opened = await apiClient.post("/api/v1/conversations/open", {
      data: { siteId },
    });
    expect(opened.status()).toBe(200);
    const { conversationId } = (await opened.json()) as OpenConversationResponse;
    expect(conversationId).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
    );

    const got = await apiClient.get(`/api/v1/conversations/${conversationId}`);
    expect(got.status()).toBe(200);
    const conversation = (await got.json()) as ConversationResponse;
    expect(conversation.id).toBe(conversationId);
    expect(conversation.siteId).toBe(siteId);
  });
});
