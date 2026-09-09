/**
 * @vitest-environment jsdom
 */
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import type { UIMessageChunk } from "ai";

import { server } from "../../../../vitest.msw-setup";
import { conversationCursors } from "../api/assistantClient";

import { createDurableTransport } from "./durableTransport";

const OPEN_MESSAGE = "22222222-2222-2222-2222-222222222222";
const TASK_ID = "00000000-0000-0000-0000-0000000000bb";
const EVENTS_URL = "http://localhost:3000/api/v1/conversations/c1/events";

function frame(eventId: number, payload: unknown): string {
  return `id: ${String(eventId)}\ndata: ${JSON.stringify(payload)}\n\n`;
}

function done(eventId: number): string {
  return `id: ${String(eventId)}\ndata: [DONE]\n\n`;
}

function eventStream(body: string): Response {
  return new HttpResponse(body, {
    status: 200,
    headers: {
      "content-type": "text/event-stream",
      "x-vercel-ai-ui-message-stream": "v1",
    },
  });
}

/** Serve one body per `after` value, and no turn in flight for the rest. */
function serveTails(bodies: ReadonlyMap<string, string>): string[] {
  const asked: string[] = [];
  server.use(
    http.get(EVENTS_URL, ({ request }) => {
      const after = new URL(request.url).searchParams.get("after") ?? "";
      asked.push(after);
      const body = bodies.get(after);
      return body === undefined
        ? new HttpResponse(null, { status: 204 })
        : eventStream(body);
    }),
  );
  return asked;
}

async function readChunks(
  stream: ReadableStream<UIMessageChunk> | null,
): Promise<UIMessageChunk[]> {
  if (stream === null) return [];
  const chunks: UIMessageChunk[] = [];
  const reader = stream.getReader();
  for (;;) {
    const next = await reader.read();
    if (next.done === true) break;
    chunks.push(next.value);
  }
  return chunks;
}

beforeEach(() => {
  sessionStorage.clear();
});

describe("createDurableTransport", () => {
  it("resumes from the cursor the snapshot read holds", async () => {
    conversationCursors.write("c1", 42);
    const asked = serveTails(new Map());

    const transport = createDurableTransport({
      conversationId: "c1",
      eventsUrlFor: (id) => `/api/v1/conversations/${id}/events`,
      api: "/api/v1/chat",
    });

    expect(await transport.reconnectToStream({ chatId: "c1" })).toBeNull();
    expect(asked).toEqual(["42"]);
  });

  it("carries a durable task's progress from the gap after the suspended turn", async () => {
    conversationCursors.write("c1", 40);
    conversationCursors.writeOpenMessage("c1", { messageId: OPEN_MESSAGE, after: 30 });
    const asked = serveTails(
      new Map([
        [
          "30",
          frame(31, { type: "start", messageId: OPEN_MESSAGE }) +
            frame(32, {
              type: "data-background-task-started",
              data: { taskId: TASK_ID, toolName: "run_control_tests_on_step" },
            }) +
            frame(39, { type: "finish", finishReason: "other" }) +
            done(40),
        ],
        [
          "40",
          frame(41, {
            type: "data-task-progress",
            id: TASK_ID,
            data: { taskId: TASK_ID, percent: 0.6, message: "Comparing controls" },
          }) + done(42),
        ],
      ]),
    );

    const transport = createDurableTransport({
      conversationId: "c1",
      eventsUrlFor: (id) => `/api/v1/conversations/${id}/events`,
      api: "/api/v1/chat",
    });

    const chunks = await readChunks(
      await transport.reconnectToStream({ chatId: "c1" }),
    );

    expect(asked).toEqual(["30", "40", "42"]);
    expect(chunks).toContainEqual({
      type: "data-task-progress",
      id: TASK_ID,
      data: { taskId: TASK_ID, percent: 0.6, message: "Comparing controls" },
    });
  });
});
