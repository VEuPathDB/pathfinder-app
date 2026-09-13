/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { toast } from "sonner";
import type { UIMessage } from "ai";

import { conversationCursors } from "../api/assistantClient";

import { THREAD_STOPPED_FOLLOWING, useChatRuntime } from "./useChatRuntime";

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

const OPEN_MESSAGE_ID = "33333333-4444-4555-8666-777777777777";
const SECOND_MESSAGE_ID = "44444444-5555-4666-8777-888888888888";
const FIRST_TASK = "00000000-0000-4000-8000-0000000000a1";
const SECOND_TASK = "00000000-0000-4000-8000-0000000000a2";
const THIRD_MESSAGE_ID = "55555555-6666-4777-8888-999999999999";

function frame(eventId: number, payload: unknown): string {
  return `id: ${String(eventId)}\ndata: ${JSON.stringify(payload)}\n\n`;
}

function doneFrame(eventId: number): string {
  return `id: ${String(eventId)}\ndata: [DONE]\n\n`;
}

/** A tail that hands over one frame per turn of the event loop, as a live one does. */
function eventStream(frames: readonly string[]): Response {
  const encoder = new TextEncoder();
  let next = 0;
  const body = new ReadableStream<Uint8Array>({
    pull: async (controller) => {
      await new Promise((resolve) => setTimeout(resolve, 0));
      const frame = frames[next];
      next += 1;
      if (frame === undefined) controller.close();
      else controller.enqueue(encoder.encode(frame));
    },
  });
  return new Response(body, {
    status: 200,
    headers: {
      "content-type": "text/event-stream",
      "x-vercel-ai-ui-message-stream": "v1",
    },
  });
}

/** The turn that parks two control-test tasks and ends its own stream. */
const PARKED_TURN = [
  frame(1, { type: "start", messageId: OPEN_MESSAGE_ID }),
  frame(2, { type: "start-step" }),
  frame(3, {
    type: "data-background-task-started",
    id: FIRST_TASK,
    data: {
      taskId: FIRST_TASK,
      toolName: "run_control_tests_on_step",
      estimatedDurationSeconds: 180,
    },
  }),
  frame(4, {
    type: "data-background-task-started",
    id: SECOND_TASK,
    data: {
      taskId: SECOND_TASK,
      toolName: "run_control_tests_on_step",
      estimatedDurationSeconds: 180,
    },
  }),
  frame(5, { type: "finish-step" }),
  frame(6, { type: "finish", finishReason: "other" }),
  doneFrame(7),
];

/** The gap after the park: both tasks report, then a turn that parks again. */
const TAIL_AFTER_FIRST_PARK = [
  ...PARKED_TURN,
  frame(8, {
    type: "data-task-progress",
    id: FIRST_TASK,
    data: { taskId: FIRST_TASK, percent: 0.5, message: "Comparing controls" },
  }),
  frame(9, {
    type: "data-task-progress",
    id: SECOND_TASK,
    data: { taskId: SECOND_TASK, percent: 0.5, message: "Comparing controls" },
  }),
  frame(10, {
    type: "data-task-completed",
    id: FIRST_TASK,
    data: { taskId: FIRST_TASK, status: "success" },
  }),
  frame(11, {
    type: "data-task-completed",
    id: SECOND_TASK,
    data: { taskId: SECOND_TASK, status: "success" },
  }),
  frame(12, { type: "start", messageId: SECOND_MESSAGE_ID }),
  frame(13, { type: "start-step" }),
  frame(14, {
    type: "data-background-task-started",
    id: FIRST_TASK,
    data: {
      taskId: FIRST_TASK,
      toolName: "geneset_enrichment",
      estimatedDurationSeconds: 60,
    },
  }),
  frame(15, { type: "finish-step" }),
  frame(16, { type: "finish", finishReason: "other" }),
];

/** A turn that runs to its own end, which leaves the thread nothing to follow. */
const RUNNING_TURN = [
  frame(1, { type: "start", messageId: OPEN_MESSAGE_ID }),
  frame(2, { type: "start-step" }),
  frame(3, { type: "text-start", id: "t" }),
  frame(4, { type: "text-delta", id: "t", delta: "132 genes" }),
  frame(5, { type: "text-end", id: "t" }),
  frame(6, { type: "finish-step" }),
  frame(7, { type: "finish", finishReason: "stop" }),
  doneFrame(8),
];

/** The turn the snapshot reported, replayed to the park it ended on. */
const SNAPSHOT_TURN_PARKS = [
  frame(1, { type: "start", messageId: OPEN_MESSAGE_ID }),
  frame(2, {
    type: "data-background-task-started",
    id: FIRST_TASK,
    data: {
      taskId: FIRST_TASK,
      toolName: "run_control_tests_on_step",
      estimatedDurationSeconds: 180,
    },
  }),
  frame(3, { type: "finish", finishReason: "other" }),
];

/** The park's own tail: the task reports, and the turn that follows it ends. */
const PARK_COMPLETES = [
  ...SNAPSHOT_TURN_PARKS,
  doneFrame(4),
  frame(5, {
    type: "data-task-completed",
    id: FIRST_TASK,
    data: { taskId: FIRST_TASK, status: "success" },
  }),
  frame(6, { type: "start", messageId: SECOND_MESSAGE_ID }),
  frame(7, { type: "finish", finishReason: "stop" }),
  doneFrame(8),
];

/** The park's tail, cut where the next turn opens: its own end is not delivered. */
const PARK_OPENS_SECOND_TURN = [
  ...PARKED_TURN,
  frame(8, {
    type: "data-task-progress",
    id: FIRST_TASK,
    data: { taskId: FIRST_TASK, percent: 0.5, message: "Comparing controls" },
  }),
  frame(9, {
    type: "data-task-completed",
    id: FIRST_TASK,
    data: { taskId: FIRST_TASK, status: "success" },
  }),
  frame(10, { type: "start", messageId: SECOND_MESSAGE_ID }),
  frame(11, { type: "start-step" }),
];

/** The second turn, replayed to the park it ends on: a turn boundary is delivered. */
const SECOND_TURN_PARKS = [
  frame(10, { type: "start", messageId: SECOND_MESSAGE_ID }),
  frame(11, { type: "start-step" }),
  frame(12, { type: "finish-step" }),
  frame(13, { type: "finish", finishReason: "other" }),
  doneFrame(14),
];

/** The turn after that park, which answers and ends the thread's work. */
const THIRD_TURN_ANSWERS = [
  ...SECOND_TURN_PARKS,
  frame(15, { type: "start", messageId: THIRD_MESSAGE_ID }),
  frame(16, { type: "text-start", id: "answer" }),
  frame(17, {
    type: "text-delta",
    id: "answer",
    delta: "2 of 2 positive controls recovered",
  }),
  frame(18, { type: "text-end", id: "answer" }),
  frame(19, { type: "finish", finishReason: "stop" }),
  doneFrame(20),
];

interface ConversationStub {
  /** This test's own thread. A thread of its own keeps every test's log apart. */
  conversationId: string;
  tailUrls: string[];
  tailUrl: (after: number) => string;
  endTurn: () => void;
  parkTurn: () => void;
}

/** The body a tail answers with, or null for no turn in flight. */
type TailSource = (after: number) => readonly string[] | null;

/** Answer each tail from the queue its cursor names, then report nothing. */
function tailsByCursor(
  bodies: ReadonlyMap<number, readonly (readonly string[])[]>,
): TailSource {
  const queues = new Map([...bodies].map(([after, queued]) => [after, [...queued]]));
  return (after) => queues.get(after)?.shift() ?? null;
}

/** The chat POST stays open, and each tail answers the body the test queued. */
function stubConversationFetch(
  tails: TailSource = () => null,
  refuseTails = false,
): ConversationStub {
  const conversationId = crypto.randomUUID();
  const eventsUrl = `/api/v1/conversations/${conversationId}/events`;
  const tailUrls: string[] = [];
  const encoder = new TextEncoder();
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
        // A tail another test's thread left running answers nothing and is not read.
        if (!url.startsWith(eventsUrl)) {
          return Promise.resolve(new Response(null, { status: 204 }));
        }
        tailUrls.push(url);
        if (refuseTails) {
          return Promise.resolve(
            new Response("the log is unreadable", { status: 500 }),
          );
        }
        const after = Number(
          new URL(url, "http://localhost").searchParams.get("after"),
        );
        const body = tails(after);
        return Promise.resolve(
          body === null ? new Response(null, { status: 204 }) : eventStream(body),
        );
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
        new Response(
          JSON.stringify({ conversationId, isNew: false, name: "Kinase genes" }),
          {
            status: 200,
            headers: { "content-type": "application/json" },
          },
        ),
      );
    }),
  );
  const write = (body: string) => {
    turn?.enqueue(encoder.encode(body));
    turn?.close();
  };
  return {
    conversationId,
    tailUrls,
    tailUrl: (after) => `${eventsUrl}?after=${String(after)}`,
    endTurn: () =>
      write(
        frame(1, { type: "start", messageId: OPEN_MESSAGE_ID }) +
          frame(2, { type: "start-step" }) +
          frame(3, { type: "finish-step" }) +
          frame(4, { type: "finish" }),
      ),
    parkTurn: () => write(PARKED_TURN.join("")),
  };
}

/** Every part the thread holds, in the order the messages carry them. */
function partsOf(messages: readonly UIMessage[]): UIMessage["parts"] {
  return messages.flatMap((message) => message.parts);
}

/** Let the pending fetches and their readers run to their next park. */
async function settle(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

async function sendAndPark(stub: ConversationStub) {
  const { result } = renderHook(() =>
    useChatRuntime({ conversationId: stub.conversationId }),
  );
  await act(async () => {
    void result.current.chat.sendMessage({ text: "run the control tests" });
  });
  await waitFor(() => {
    expect(result.current.chat.status).toBe("submitted");
  });
  stub.parkTurn();
  return result;
}

beforeEach(() => {
  sessionStorage.clear();
  vi.mocked(toast.error).mockClear();
});

describe("useChatRuntime reattach", () => {
  it("opens no tail on a thread the snapshot left with no open message", async () => {
    const stub = stubConversationFetch();

    const { result } = renderHook(() =>
      useChatRuntime({ conversationId: stub.conversationId, resume: true }),
    );

    await act(async () => {
      void result.current.chat.sendMessage({ text: "show me kinase genes" });
    });
    await waitFor(() => {
      expect(result.current.chat.status).toBe("submitted");
    });
    expect(stub.tailUrls).toEqual([]);

    stub.endTurn();
    await waitFor(() => {
      expect(result.current.chat.status).toBe("ready");
    });
    await settle();
    expect(stub.tailUrls).toEqual([]);
  });

  it("reattaches to the message the snapshot left open", async () => {
    const stub = stubConversationFetch();
    conversationCursors.write(stub.conversationId, 40);
    conversationCursors.writeOpenMessage(stub.conversationId, {
      messageId: OPEN_MESSAGE_ID,
      after: 30,
    });

    renderHook(() =>
      useChatRuntime({ conversationId: stub.conversationId, resume: true }),
    );

    await waitFor(() => {
      expect(stub.tailUrls).toEqual([stub.tailUrl(30)]);
    });
    await settle();
    expect(stub.tailUrls).toEqual([stub.tailUrl(30)]);
  });

  it("follows the turn the snapshot reports in flight once, and no further", async () => {
    const stub = stubConversationFetch(tailsByCursor(new Map([[0, [RUNNING_TURN]]])));

    renderHook(() =>
      useChatRuntime({
        conversationId: stub.conversationId,
        resume: true,
        turnInFlight: true,
      }),
    );

    await waitFor(() => {
      expect(stub.tailUrls).toEqual([stub.tailUrl(0)]);
    });
    await settle();
    expect(stub.tailUrls).toEqual([stub.tailUrl(0)]);
  });

  it("follows the park a snapshot turn ends on, and drops the turn once it is read", async () => {
    const stub = stubConversationFetch(
      tailsByCursor(new Map([[0, [SNAPSHOT_TURN_PARKS, PARK_COMPLETES]]])),
    );

    renderHook(() =>
      useChatRuntime({
        conversationId: stub.conversationId,
        resume: true,
        turnInFlight: true,
      }),
    );

    await waitFor(() => {
      expect(stub.tailUrls).toEqual([stub.tailUrl(0), stub.tailUrl(0)]);
    });
    await settle();
    expect(stub.tailUrls).toEqual([stub.tailUrl(0), stub.tailUrl(0)]);
  });

  it("opens one tail per park, whatever the parked turn started", async () => {
    const stub = stubConversationFetch(
      tailsByCursor(new Map([[0, [TAIL_AFTER_FIRST_PARK]]])),
    );

    const result = await sendAndPark(stub);

    await waitFor(() => {
      expect(stub.tailUrls).toEqual([stub.tailUrl(0), stub.tailUrl(7)]);
    });
    await settle();
    expect(stub.tailUrls).toEqual([stub.tailUrl(0), stub.tailUrl(7)]);
    expect(result.current.chat.status).toBe("ready");
  });

  it("carries the parked tasks' progress and outcome onto the thread", async () => {
    const stub = stubConversationFetch(
      tailsByCursor(new Map([[0, [TAIL_AFTER_FIRST_PARK]]])),
    );

    const result = await sendAndPark(stub);

    await waitFor(
      () => {
        expect(stub.tailUrls).toEqual([stub.tailUrl(0), stub.tailUrl(7)]);
        expect(partsOf(result.current.chat.messages)).toContainEqual({
          type: "data-task-completed",
          id: SECOND_TASK,
          data: { taskId: SECOND_TASK, status: "success" },
        });
      },
      { timeout: 5000 },
    );
    expect(partsOf(result.current.chat.messages)).toContainEqual({
      type: "data-task-progress",
      id: FIRST_TASK,
      data: { taskId: FIRST_TASK, percent: 0.5, message: "Comparing controls" },
    });
  });

  it("follows the turn boundary a tail delivers while the same message stays open", async () => {
    const stub = stubConversationFetch(
      tailsByCursor(
        new Map([
          [0, [PARK_OPENS_SECOND_TURN]],
          [7, [SECOND_TURN_PARKS, THIRD_TURN_ANSWERS]],
        ]),
      ),
    );

    const result = await sendAndPark(stub);

    await waitFor(
      () => {
        expect(stub.tailUrls).toEqual([
          stub.tailUrl(0),
          stub.tailUrl(7),
          stub.tailUrl(14),
          stub.tailUrl(7),
        ]);
        expect(partsOf(result.current.chat.messages)).toContainEqual({
          type: "text",
          text: "2 of 2 positive controls recovered",
          state: "done",
        });
      },
      { timeout: 5000 },
    );
    await settle();
    expect(stub.tailUrls).toEqual([
      stub.tailUrl(0),
      stub.tailUrl(7),
      stub.tailUrl(14),
      stub.tailUrl(7),
    ]);
  });

  it("tells the user when the thread cannot follow its running work", async () => {
    const stub = stubConversationFetch(() => null, true);
    conversationCursors.write(stub.conversationId, 40);
    conversationCursors.writeOpenMessage(stub.conversationId, {
      messageId: OPEN_MESSAGE_ID,
      after: 30,
    });

    const { result } = renderHook(() =>
      useChatRuntime({ conversationId: stub.conversationId, resume: true }),
    );

    await waitFor(() => {
      expect(vi.mocked(toast.error)).toHaveBeenCalledWith(THREAD_STOPPED_FOLLOWING);
    });
    await settle();
    expect(stub.tailUrls).toEqual([stub.tailUrl(30)]);
    expect(vi.mocked(toast.error)).toHaveBeenCalledTimes(1);
    // The SDK marks its own stream failed; no turn runs, so the composer is free.
    expect(result.current.chat.status).toBe("error");
  });
});
