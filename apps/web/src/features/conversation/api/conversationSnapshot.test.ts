/**
 * @vitest-environment jsdom
 */
import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { APIError } from "@/lib/api/http";

import { server } from "../../../../vitest.msw-setup";

import { conversationCursors } from "./assistantClient";
import {
  conversationSnapshotOptions,
  loadConversationSnapshot,
} from "./conversationSnapshot";

const SNAPSHOT_ROUTE =
  "http://localhost:3000/api/v1/conversations/:conversationId/events/snapshot";

function serveSnapshot(body: { chunks: unknown[]; cursor: number }): string[] {
  const seen: string[] = [];
  server.use(
    http.get(SNAPSHOT_ROUTE, ({ request }) => {
      seen.push(new URL(request.url).pathname);
      return HttpResponse.json(body);
    }),
  );
  return seen;
}

beforeEach(() => {
  sessionStorage.clear();
});

describe("loadConversationSnapshot", () => {
  it("reads the thread's snapshot endpoint", async () => {
    const seen = serveSnapshot({ cursor: 0, chunks: [] });

    await loadConversationSnapshot("c1");

    expect(seen).toEqual(["/api/v1/conversations/c1/events/snapshot"]);
  });

  it("rebuilds the transcript the snapshot holds", async () => {
    serveSnapshot({
      cursor: 7,
      chunks: [
        { type: "user-message", message: { id: "u1", role: "user", parts: [] } },
        { type: "start", messageId: "a1" },
        { type: "text-start", id: "t" },
        { type: "text-delta", id: "t", delta: "hello" },
        { type: "text-end", id: "t" },
        { type: "finish", finishReason: "stop" },
        { type: "done" },
      ],
    });

    const { messages } = await loadConversationSnapshot("c1");

    expect(messages.map((message) => message.id)).toEqual(["u1", "a1"]);
    expect(messages[1]?.parts).toEqual([
      { type: "text", text: "hello", state: "done" },
    ]);
  });

  it("advances the resume cursor to the one the snapshot reports", async () => {
    serveSnapshot({ cursor: 9, chunks: [] });

    await loadConversationSnapshot("c1");

    expect(conversationCursors.read("c1")).toBe(9);
  });

  it("keeps the resume cursor a stream already recorded", async () => {
    // A snapshot taken before the stream's last frame reports a lower cursor.
    // Writing it back would replay every frame between the two.
    conversationCursors.write("c1", 42);
    serveSnapshot({ cursor: 7, chunks: [] });

    await loadConversationSnapshot("c1");

    expect(conversationCursors.read("c1")).toBe(42);
  });

  it("reports the turn a snapshot that ends at the prompt left running", async () => {
    serveSnapshot({
      cursor: 220744,
      chunks: [
        { type: "user-message", message: { id: "u1", role: "user", parts: [] } },
      ],
    });

    expect((await loadConversationSnapshot("c1")).turnInFlight).toBe(true);
  });

  it("reads a conversation with no event log as an empty transcript", async () => {
    server.use(http.get(SNAPSHOT_ROUTE, () => new HttpResponse(null, { status: 404 })));

    expect(await loadConversationSnapshot("gone")).toEqual({
      messages: [],
      turnInFlight: false,
    });
  });

  it("reports any other failure with the sentence the server offered", async () => {
    server.use(
      http.get(SNAPSHOT_ROUTE, () =>
        HttpResponse.json({ detail: "Event log unreadable" }, { status: 500 }),
      ),
    );

    const failure = await loadConversationSnapshot("c1").then(
      () => null,
      (err: unknown) => err,
    );

    expect(failure).toBeInstanceOf(APIError);
    if (!(failure instanceof APIError)) return;
    expect(failure.status).toBe(500);
    expect(failure.message).toBe("Event log unreadable");
  });
});

describe("conversationSnapshotOptions", () => {
  it("re-reads the transcript for every mount", async () => {
    // A turn appends messages the cached snapshot does not have, so a cached
    // snapshot served to a later mount shows a shorter transcript than exists.
    const client = new QueryClient();
    const options = conversationSnapshotOptions("c1");
    const queryFn = vi.fn().mockResolvedValue([]);
    const observer = new QueryObserver(client, { ...options, queryFn });

    const unsubscribe = observer.subscribe(() => {});
    await observer.refetch();
    unsubscribe();
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(client.getQueryData(options.queryKey)).toBe(undefined);
  });

  it("does not refetch while a single mount is open", () => {
    expect(conversationSnapshotOptions("c1").staleTime).toBe(Infinity);
  });
});
