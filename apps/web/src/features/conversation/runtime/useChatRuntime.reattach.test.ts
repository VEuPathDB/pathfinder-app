/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";

import { conversationCursors } from "../api/assistantClient";

import { useChatRuntime } from "./useChatRuntime";

const CONVERSATION_ID = "11111111-2222-4333-8444-666666666666";
const OPEN_MESSAGE_ID = "33333333-4444-4555-8666-777777777777";

const BEGIN_BODY = {
  conversationId: CONVERSATION_ID,
  isNew: false,
  name: "Kinase genes",
};

function sseFrame(eventId: number, payload: unknown): Uint8Array {
  return new TextEncoder().encode(
    `id: ${String(eventId)}\ndata: ${JSON.stringify(payload)}\n\n`,
  );
}

interface ConversationStub {
  tailUrls: string[];
  reportNoTurnInFlight: () => void;
  endTurn: () => void;
}

/** The chat POST stays open, and the tail answers when the test says so. */
function stubConversationFetch(): ConversationStub {
  const tailUrls: string[] = [];
  let releaseTail: (response: Response) => void = () => undefined;
  const tail = new Promise<Response>((resolve) => {
    releaseTail = resolve;
  });
  let turn: ReadableStreamDefaultController<Uint8Array> | undefined;
  const turnBody = new ReadableStream<Uint8Array>({
    start: (controller) => {
      turn = controller;
    },
  });
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input instanceof Request ? input.url : input);
      if (url.includes("/events")) {
        tailUrls.push(url);
        return tail;
      }
      if (url.includes("/api/v1/chat")) {
        return Promise.resolve(
          new Response(turnBody, {
            status: 200,
            headers: {
              "content-type": "text/event-stream",
              "x-vercel-ai-ui-message-stream": "v1",
            },
          }),
        );
      }
      return Promise.resolve(
        new Response(JSON.stringify(BEGIN_BODY), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    }),
  );
  return {
    tailUrls,
    reportNoTurnInFlight: () => {
      releaseTail(new Response(null, { status: 204 }));
    },
    endTurn: () => {
      turn?.enqueue(sseFrame(1, { type: "start", messageId: OPEN_MESSAGE_ID }));
      turn?.enqueue(sseFrame(2, { type: "start-step" }));
      turn?.enqueue(sseFrame(3, { type: "finish-step" }));
      turn?.enqueue(sseFrame(4, { type: "finish" }));
      turn?.close();
    },
  };
}

/** Let the pending fetches and their readers run to their next park. */
async function settle(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

beforeEach(() => {
  sessionStorage.clear();
});

describe("useChatRuntime reattach", () => {
  it("opens no tail on a thread the snapshot left with no open message", async () => {
    const stub = stubConversationFetch();

    const { result } = renderHook(() =>
      useChatRuntime({ conversationId: CONVERSATION_ID, resume: true }),
    );

    await act(async () => {
      void result.current.chat.sendMessage({ text: "show me kinase genes" });
    });
    await waitFor(() => {
      expect(result.current.chat.status).toBe("submitted");
    });

    stub.reportNoTurnInFlight();
    await settle();

    expect(result.current.chat.status).toBe("submitted");
    expect(stub.tailUrls).toEqual([]);

    stub.endTurn();
    await waitFor(() => {
      expect(result.current.chat.status).toBe("ready");
    });
  });

  it("reattaches to the message the snapshot left open", async () => {
    const stub = stubConversationFetch();
    conversationCursors.write(CONVERSATION_ID, 40);
    conversationCursors.writeOpenMessage(CONVERSATION_ID, {
      messageId: OPEN_MESSAGE_ID,
      after: 30,
    });

    renderHook(() => useChatRuntime({ conversationId: CONVERSATION_ID, resume: true }));

    await waitFor(() => {
      expect(stub.tailUrls).toHaveLength(1);
    });
    expect(stub.tailUrls[0]).toBe(
      `/api/v1/conversations/${CONVERSATION_ID}/events?after=30`,
    );

    stub.reportNoTurnInFlight();
    await settle();
  });
});
