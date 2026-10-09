/**
 * @vitest-environment jsdom
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useFirstMessageStore } from "@/state/useFirstMessageStore";

import { useChatRuntime } from "./useChatRuntime";

const CONVERSATION_ID = "66666666-7777-4888-8999-aaaaaaaaaaaa";
const TURN_MESSAGE_ID = "77777777-8888-4999-8aaa-bbbbbbbbbbbb";
const PROMPT = "Describe the virulence factors of this strain.";
const NOTICE =
  "Claude Sonnet 5.5 declined this request. Try rephrasing it, or pick a different model in Settings.";

function frame(eventId: number, payload: unknown): string {
  return `id: ${String(eventId)}\ndata: ${JSON.stringify(payload)}\n\n`;
}

function declinedTurn(promptId: string): Response {
  const body = [
    frame(1, { type: "start", messageId: TURN_MESSAGE_ID }),
    frame(11, { type: "reasoning-start", id: "r" }),
    frame(12, { type: "reasoning-delta", id: "r", delta: "thinking about it" }),
    frame(13, { type: "reasoning-end", id: "r" }),
    frame(14, {
      type: "data-turn-withdrawn",
      data: { errorText: NOTICE, messageId: promptId },
    }),
    frame(15, { type: "error", errorText: NOTICE }),
    frame(16, { type: "finish", finishReason: "stop" }),
    `id: 17\ndata: [DONE]\n\n`,
  ].join("");
  return new Response(body, {
    status: 200,
    headers: {
      "content-type": "text/event-stream",
      "x-vercel-ai-ui-message-stream": "v1",
    },
  });
}

const sentRequest = { lastMessageId: "" };

function stubDecliningTurn(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input instanceof Request ? input.url : input);
      if (url.includes("/api/v1/chat")) {
        const sent = JSON.parse(String(init?.body)) as {
          messages: { id: string }[];
        };
        sentRequest.lastMessageId = sent.messages.at(-1)?.id ?? "";
        return Promise.resolve(declinedTurn(sentRequest.lastMessageId));
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({ conversationId: CONVERSATION_ID, isNew: false, name: "" }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useChatRuntime, a withdrawn prompt", () => {
  it("leaves the thread without the prompt and puts its words back in the composer", async () => {
    stubDecliningTurn();
    const { result } = renderHook(() =>
      useChatRuntime({ conversationId: CONVERSATION_ID }),
    );

    await act(async () => {
      await result.current.chat.sendMessage({ text: PROMPT });
    });

    await waitFor(() => {
      expect(result.current.chat.messages.map((message) => message.role)).toEqual([
        "assistant",
      ]);
    });
    expect(sentRequest.lastMessageId).not.toBe("");
    await waitFor(() => {
      expect(result.current.chat.messages[0]?.parts).toEqual([
        {
          type: "data-turn-withdrawn",
          data: { errorText: NOTICE, messageId: sentRequest.lastMessageId },
        },
      ]);
    });
    expect(result.current.runtime.thread.composer.getState().text).toBe(PROMPT);
    expect(useFirstMessageStore.getState().byConversation[CONVERSATION_ID]).toBe(
      undefined,
    );
  });
});
