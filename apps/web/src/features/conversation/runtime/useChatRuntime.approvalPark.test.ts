/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";

import { useChatRuntime } from "./useChatRuntime";

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

const MESSAGE_ID = "66666666-7777-4888-8999-aaaaaaaaaaaa";
const TASK_ID = "00000000-0000-4000-8000-0000000000b1";

function frame(eventId: number, payload: unknown): string {
  return `id: ${String(eventId)}\ndata: ${JSON.stringify(payload)}\n\n`;
}

function doneFrame(eventId: number): string {
  return `id: ${String(eventId)}\ndata: [DONE]\n\n`;
}

const ASKS_APPROVAL = [
  frame(1, { type: "start", messageId: MESSAGE_ID }),
  frame(2, { type: "finish", finishReason: "other" }),
  doneFrame(3),
].join("");

const PARKS_AFTER_APPROVAL = [
  frame(4, { type: "start", messageId: MESSAGE_ID }),
  frame(5, {
    type: "data-background-task-started",
    id: TASK_ID,
    data: {
      taskId: TASK_ID,
      toolName: "optimize_search_parameters",
      estimatedDurationSeconds: 900,
    },
  }),
  frame(6, { type: "finish", finishReason: "other" }),
  doneFrame(7),
].join("");

function stream(body: string): Response {
  return new Response(new TextEncoder().encode(body), {
    status: 200,
    headers: {
      "content-type": "text/event-stream",
      "x-vercel-ai-ui-message-stream": "v1",
    },
  });
}

function stubFetch(conversationId: string, turns: string[]): string[] {
  const tails: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input instanceof Request ? input.url : input);
      if (url.includes("/events")) {
        if (url.includes(conversationId)) tails.push(url);
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      if (url.includes("/api/v1/chat")) {
        return Promise.resolve(stream(turns.shift() ?? ""));
      }
      return Promise.resolve(
        new Response(JSON.stringify({ conversationId, isNew: false, name: "Sweep" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    }),
  );
  return tails;
}

beforeEach(() => {
  sessionStorage.clear();
});

describe("useChatRuntime after an approval", () => {
  it("follows a park the approved turn ends on, on the message it kept open", async () => {
    const conversationId = crypto.randomUUID();
    const tails = stubFetch(conversationId, [ASKS_APPROVAL, PARKS_AFTER_APPROVAL]);
    const { result } = renderHook(() => useChatRuntime({ conversationId }));

    await act(async () => {
      void result.current.chat.sendMessage({ text: "sweep the version" });
    });
    await waitFor(() => {
      expect(tails).not.toHaveLength(0);
      expect(result.current.chat.status).toBe("ready");
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    const beforeApproval = tails.length;

    await act(async () => {
      void result.current.chat.sendMessage({ text: "approved" });
    });

    await waitFor(() => {
      expect(tails.length).toBeGreaterThan(beforeApproval);
    });
  });
});
