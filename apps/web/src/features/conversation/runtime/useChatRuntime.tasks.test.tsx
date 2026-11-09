/**
 * @vitest-environment jsdom
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { tasksListOptions } from "../api/tasks";
import { useChatRuntime } from "./useChatRuntime";

const CONVERSATION_ID = "88888888-9999-4aaa-8bbb-cccccccccccc";
const TURN_MESSAGE_ID = "99999999-aaaa-4bbb-8ccc-dddddddddddd";

function frame(eventId: number, payload: unknown): string {
  return `id: ${String(eventId)}\ndata: ${JSON.stringify(payload)}\n\n`;
}

function buildTurn(): Response {
  const body = [
    frame(1, { type: "start", messageId: TURN_MESSAGE_ID }),
    frame(2, { type: "data-background-task-started", data: {} }),
    frame(3, { type: "finish", finishReason: "stop" }),
    `id: 4\ndata: [DONE]\n\n`,
  ].join("");
  return new Response(body, {
    status: 200,
    headers: {
      "content-type": "text/event-stream",
      "x-vercel-ai-ui-message-stream": "v1",
    },
  });
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input instanceof Request ? input.url : input);
      if (url.includes("/api/v1/chat")) return Promise.resolve(buildTurn());
      return Promise.resolve(
        new Response(
          JSON.stringify({ conversationId: CONVERSATION_ID, isNew: false, name: "" }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useChatRuntime, a background task", () => {
  it("refreshes the conversation's task list when a task starts", async () => {
    const client = new QueryClient();
    const key = tasksListOptions(CONVERSATION_ID).queryKey;
    client.setQueryData(key, { tasks: [] });
    const { result } = renderHook(
      () => useChatRuntime({ conversationId: CONVERSATION_ID }),
      {
        wrapper: ({ children }: { children: ReactNode }) => (
          <QueryClientProvider client={client}>{children}</QueryClientProvider>
        ),
      },
    );

    await act(async () => {
      await result.current.chat.sendMessage({ text: "Run the controls." });
    });

    await waitFor(() => {
      expect(client.getQueryState(key)?.isInvalidated).toBe(true);
    });
  });
});
