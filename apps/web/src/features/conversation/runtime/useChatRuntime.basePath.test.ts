/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";

import { useChatRuntime } from "./useChatRuntime";

const CONVERSATION_ID = "66666666-7777-4888-8999-aaaaaaaaaaaa";

/** Answer every call a send makes, and record the address of each one. */
function stubSendFetch(): string[] {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input instanceof Request ? input.url : input);
      urls.push(url);
      if (url.endsWith("/api/v1/chat")) {
        return Promise.resolve(
          new Response(new ReadableStream<Uint8Array>({ start: (c) => c.close() }), {
            status: 200,
            headers: {
              "content-type": "text/event-stream",
              "x-vercel-ai-ui-message-stream": "v1",
            },
          }),
        );
      }
      return Promise.resolve(
        Response.json({
          conversationId: CONVERSATION_ID,
          isNew: false,
          name: "Kinases",
        }),
      );
    }),
  );
  return urls;
}

beforeEach(() => {
  sessionStorage.clear();
});

describe("the chat transport's addresses", () => {
  it("posts a turn under the base path on the page's origin", async () => {
    const urls = stubSendFetch();
    const { result } = renderHook(() =>
      useChatRuntime({ conversationId: CONVERSATION_ID }),
    );

    await act(async () => {
      void result.current.chat.sendMessage({ text: "list kinases" });
    });
    await waitFor(() => {
      expect(result.current.chat.status).not.toBe("submitted");
    });

    expect(urls).toContain("http://localhost:3000/pathfinder/api/v1/chat");
  });
});
