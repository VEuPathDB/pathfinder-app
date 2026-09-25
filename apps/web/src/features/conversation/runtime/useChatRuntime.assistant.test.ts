/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";

import { useChatRuntime } from "./useChatRuntime";

const CONVERSATION_ID = "22222222-3333-4444-8555-666666666666";

interface Sent {
  begin: Record<string, unknown>[];
  chat: Record<string, unknown>[];
}

function readBody(init: RequestInit | undefined): Record<string, unknown> {
  return JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
}

/** Answer both calls a send makes, and record what each one carried. */
function stubSendFetch(isNew: boolean): Sent {
  const sent: Sent = { begin: [], chat: [] };
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input instanceof Request ? input.url : input);
      if (url.includes("/api/v1/models")) {
        return Promise.resolve(Response.json({ models: [], phaseDefaults: {} }));
      }
      if (url.includes("/api/v1/chat")) {
        sent.chat.push(readBody(init));
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
      sent.begin.push(readBody(init));
      return Promise.resolve(
        new Response(
          JSON.stringify({ conversationId: CONVERSATION_ID, isNew, name: "Site help" }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );
    }),
  );
  return sent;
}

async function sendOneMessage(assistantId: string | undefined): Promise<void> {
  const { result } = renderHook(() =>
    useChatRuntime({
      conversationId: CONVERSATION_ID,
      ...(assistantId !== undefined && { assistantId }),
    }),
  );
  await act(async () => {
    void result.current.chat.sendMessage({ text: "which sites can I use" });
  });
  await waitFor(() => {
    expect(result.current.chat.status).not.toBe("submitted");
  });
}

beforeEach(() => {
  sessionStorage.clear();
});

describe("the assistant a turn names", () => {
  it("creates the thread under the named assistant and names it on that turn", async () => {
    const sent = stubSendFetch(true);

    await sendOneMessage("site_help");

    expect(sent.begin[0]?.["assistantId"]).toBe("site_help");
    expect(sent.chat[0]?.["assistantId"]).toBe("site_help");
  });

  it("names no assistant on a turn of a thread that already existed", async () => {
    const sent = stubSendFetch(false);

    await sendOneMessage("site_help");

    expect(sent.begin[0]?.["assistantId"]).toBe("site_help");
    expect(sent.chat[0]).not.toHaveProperty("assistantId");
  });

  it("names no assistant at all when the caller has none", async () => {
    const sent = stubSendFetch(true);

    await sendOneMessage(undefined);

    expect(sent.begin[0]).not.toHaveProperty("assistantId");
    expect(sent.chat[0]).not.toHaveProperty("assistantId");
  });
});
