/**
 * @vitest-environment jsdom
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useThreadModeStore } from "@/state/useThreadModeStore";

import { useChatRuntime } from "./useChatRuntime";

const CONVERSATION_ID = "44444444-5555-4666-8777-888888888888";

function readBody(init: RequestInit | undefined): Record<string, unknown> {
  return JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
}

function stubSendFetch(): Record<string, unknown>[] {
  const chat: Record<string, unknown>[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input instanceof Request ? input.url : input);
      if (url.includes("/api/v1/chat")) {
        chat.push(readBody(init));
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
        new Response(
          JSON.stringify({ conversationId: CONVERSATION_ID, isNew: false, name: "" }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );
    }),
  );
  return chat;
}

beforeEach(() => {
  sessionStorage.clear();
  useThreadModeStore.setState({ modes: {} });
});

async function sentBody(): Promise<Record<string, unknown> | undefined> {
  const chat = stubSendFetch();
  const { result } = renderHook(() =>
    useChatRuntime({ conversationId: CONVERSATION_ID }),
  );
  await act(async () => {
    void result.current.chat.sendMessage({ text: "kinases in P. falciparum" });
  });
  await waitFor(() => {
    expect(result.current.chat.status).not.toBe("submitted");
  });
  return chat[0];
}

describe("the mode a turn carries", () => {
  it("sends the mode picked for the thread", async () => {
    useThreadModeStore.getState().setMode(CONVERSATION_ID, "explore");
    expect((await sentBody())?.["mode"]).toBe("explore");
  });

  it("sends auto when nothing was picked", async () => {
    expect((await sentBody())?.["mode"]).toBe("auto");
  });
});
