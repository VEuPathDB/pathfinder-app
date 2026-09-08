/**
 * @vitest-environment jsdom
 */
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { server } from "../../../../vitest.msw-setup";
import { conversationCursors } from "../api/assistantClient";

import { createDurableTransport } from "./durableTransport";

beforeEach(() => {
  sessionStorage.clear();
});

describe("createDurableTransport", () => {
  it("resumes from the cursor the snapshot read holds", async () => {
    conversationCursors.write("c1", 42);
    const seen: string[] = [];
    server.use(
      http.get(
        "http://localhost:3000/api/v1/conversations/c1/events",
        ({ request }) => {
          seen.push(new URL(request.url).search);
          return new HttpResponse(null, { status: 204 });
        },
      ),
    );

    const transport = createDurableTransport({
      conversationId: "c1",
      eventsUrlFor: (id) => `/api/v1/conversations/${id}/events`,
      api: "/api/v1/chat",
    });

    expect(await transport.reconnectToStream({ chatId: "c1" })).toBeNull();
    expect(seen).toEqual(["?after=42"]);
  });
});
