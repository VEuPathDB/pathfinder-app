import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as HttpModule from "@/lib/api/http";

// The chunk-to-message reduction is the client package's conformance suite.
// What is app-owned here is the request, the 404 rule and the query options.
vi.mock("@/lib/api/http", async (importOriginal) => ({
  ...(await importOriginal<typeof HttpModule>()),
  requestJson: vi.fn(),
}));

import { APIError, requestJson } from "@/lib/api/http";

import {
  conversationSnapshotOptions,
  loadSnapshotMessages,
} from "./conversationSnapshot";

const mockRequestJson = vi.mocked(requestJson);

beforeEach(() => {
  mockRequestJson.mockReset();
});

describe("loadSnapshotMessages", () => {
  it("reads the thread's snapshot endpoint", async () => {
    mockRequestJson.mockResolvedValue({ cursor: 0, chunks: [] });

    await loadSnapshotMessages("c1");

    expect(mockRequestJson.mock.calls[0]?.[1]).toBe(
      "/api/v1/conversations/c1/events/snapshot",
    );
  });

  it("rebuilds the transcript the snapshot holds", async () => {
    mockRequestJson.mockResolvedValue({
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

    const messages = await loadSnapshotMessages("c1");

    expect(messages.map((message) => message.id)).toEqual(["u1", "a1"]);
    expect(messages[1]?.parts).toEqual([
      { type: "text", text: "hello", state: "done" },
    ]);
  });

  it("reads a conversation with no event log as an empty transcript", async () => {
    mockRequestJson.mockRejectedValue(
      new APIError("not found", {
        status: 404,
        statusText: "Not Found",
        url: "/api/v1/conversations/gone/events/snapshot",
        data: null,
      }),
    );

    expect(await loadSnapshotMessages("gone")).toEqual([]);
  });

  it("reports any other failure to the caller", async () => {
    mockRequestJson.mockRejectedValue(
      new APIError("boom", {
        status: 500,
        statusText: "Server Error",
        url: "/api/v1/conversations/c1/events/snapshot",
        data: null,
      }),
    );

    await expect(loadSnapshotMessages("c1")).rejects.toThrow(APIError);
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
