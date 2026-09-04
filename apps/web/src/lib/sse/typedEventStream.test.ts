/**
 * Tests for the shared typed-event SSE helper.
 *
 * Mocks `fetch` with a `ReadableStream` that emits canned SSE frames and
 * asserts the async generator yields the decoded JSON payloads in order.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { APIError } from "@/lib/api/http";
import { streamTypedEvents } from "./typedEventStream";

async function collectError(stream: AsyncGenerator<unknown>): Promise<unknown> {
  try {
    for await (const _ of stream) void _;
  } catch (err: unknown) {
    return err;
  }
  return null;
}

function streamFromChunks(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

function stubFetchWithStream(
  body: ReadableStream<Uint8Array> | null,
  ok = true,
  status = 200,
): ReturnType<typeof vi.fn> {
  const fetchSpy = vi.fn(
    async () =>
      ({
        ok,
        status,
        statusText: ok ? "OK" : "Internal Server Error",
        body,
        headers: new Headers({ "content-type": "text/event-stream" }),
      }) as unknown as Response,
  );
  vi.stubGlobal("fetch", fetchSpy);
  return fetchSpy;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("streamTypedEvents", () => {
  it("parses SSE frames into typed events", async () => {
    stubFetchWithStream(
      streamFromChunks([
        'event: sweep_point\ndata: {"x":1,"y":2}\n\n',
        'event: sweep_point\ndata: {"x":3,"y":4}\n\n',
        "data: [DONE]\n\n",
      ]),
    );

    const events: unknown[] = [];
    for await (const e of streamTypedEvents<{ x: number; y: number }>(
      "/api/v1/experiments/1/threshold-sweep",
    )) {
      events.push(e);
    }

    expect(events).toEqual([
      { x: 1, y: 2 },
      { x: 3, y: 4 },
    ]);
  });

  it("returns immediately on [DONE] even when more data follows", async () => {
    stubFetchWithStream(
      streamFromChunks([
        'event: foo\ndata: {"v":1}\n\n',
        "data: [DONE]\n\n",
        'event: foo\ndata: {"v":2}\n\n',
      ]),
    );

    const events: unknown[] = [];
    for await (const e of streamTypedEvents<{ v: number }>("/x")) {
      events.push(e);
    }

    expect(events).toEqual([{ v: 1 }]);
  });

  it("handles frames split across chunk boundaries", async () => {
    stubFetchWithStream(
      streamFromChunks(['event: foo\ndata: {"a', '":"hello"}\n\n', "data: [DONE]\n\n"]),
    );

    const events: unknown[] = [];
    for await (const e of streamTypedEvents<{ a: string }>("/x")) {
      events.push(e);
    }

    expect(events).toEqual([{ a: "hello" }]);
  });

  it("skips frames with malformed JSON payloads", async () => {
    stubFetchWithStream(
      streamFromChunks([
        "event: foo\ndata: not-json\n\n",
        'event: foo\ndata: {"ok":true}\n\n',
        "data: [DONE]\n\n",
      ]),
    );

    const events: unknown[] = [];
    for await (const e of streamTypedEvents<{ ok: boolean }>("/x")) {
      events.push(e);
    }

    expect(events).toEqual([{ ok: true }]);
  });

  it("skips keep-alive / comment frames that carry no data line", async () => {
    stubFetchWithStream(
      streamFromChunks([
        ": keepalive\n\n",
        'event: foo\ndata: {"v":1}\n\n',
        "data: [DONE]\n\n",
      ]),
    );

    const events: unknown[] = [];
    for await (const e of streamTypedEvents<{ v: number }>("/x")) {
      events.push(e);
    }

    expect(events).toEqual([{ v: 1 }]);
  });

  it("reports the transport status when the refusal says nothing", async () => {
    stubFetchWithStream(null, false, 500);

    const error = await collectError(streamTypedEvents("/x"));
    expect(error).toBeInstanceOf(APIError);
    expect((error as APIError).status).toBe(500);
    expect((error as APIError).message).toBe("HTTP 500 Internal Server Error");
  });

  it("names the API's reason in the thrown error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ detail: "Missing required X-Requested-With header" }),
            {
              status: 403,
              statusText: "Forbidden",
              headers: { "content-type": "application/json" },
            },
          ),
      ),
    );

    await expect(async () => {
      for await (const _ of streamTypedEvents("/x", { method: "POST", body: {} })) {
        void _;
      }
    }).rejects.toThrow("Missing required X-Requested-With header");
  });

  it("shows the field message a refused stream carries, never a transport line", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              title: "Invalid request",
              status: 403,
              errors: [
                { path: "siteId", message: "This account cannot read plasmodb" },
              ],
            }),
            {
              status: 403,
              statusText: "Forbidden",
              headers: { "content-type": "application/problem+json" },
            },
          ),
      ),
    );

    const error = await collectError(
      streamTypedEvents("/x", { method: "POST", body: {} }),
    );
    expect(error).toBeInstanceOf(APIError);
    expect((error as APIError).message).toBe("This account cannot read plasmodb");
  });

  it("throws when the response body is null", async () => {
    stubFetchWithStream(null, true, 200);

    await expect(async () => {
      for await (const _ of streamTypedEvents("/x")) {
        // unreachable
      }
    }).rejects.toThrow(/no response body/);
  });

  it("posts with a JSON body and content-type header when method=POST and body is given", async () => {
    const fetchSpy = stubFetchWithStream(streamFromChunks(["data: [DONE]\n\n"]));

    const events: unknown[] = [];
    for await (const e of streamTypedEvents<{ ok: boolean }>("/x", {
      method: "POST",
      body: { p: 1 },
    })) {
      events.push(e);
    }

    expect(events).toEqual([]);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const call = fetchSpy.mock.calls[0] ?? [];
    const init = call[1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"p":1}');
    const headers = init.headers as Record<string, string>;
    expect(headers["Accept"]).toBe("text/event-stream");
    expect(headers["Content-Type"]).toBe("application/json");
  });

  it("sends the CSRF header the API demands on state-changing requests", async () => {
    const fetchSpy = stubFetchWithStream(streamFromChunks(["data: [DONE]\n\n"]));

    for await (const _ of streamTypedEvents("/api/v1/experiments", {
      method: "POST",
      body: { siteId: "plasmodb" },
    })) {
      void _;
    }

    const call = fetchSpy.mock.calls[0] ?? [];
    const headers = (call[1] as RequestInit).headers as Record<string, string>;
    expect(headers["X-Requested-With"]).toBe("XMLHttpRequest");
  });

  it("defaults to GET without a body or content-type header", async () => {
    const fetchSpy = stubFetchWithStream(streamFromChunks(["data: [DONE]\n\n"]));

    const events: unknown[] = [];
    for await (const e of streamTypedEvents<{ ok: boolean }>("/x")) {
      events.push(e);
    }
    expect(events).toEqual([]);

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const call = fetchSpy.mock.calls[0] ?? [];
    const init = call[1] as RequestInit;
    expect(init.method).toBe("GET");
    expect(init.body).toBeUndefined();
    expect(init.credentials).toBe("include");
    const headers = init.headers as Record<string, string>;
    expect(headers["Accept"]).toBe("text/event-stream");
    expect(headers["Content-Type"]).toBeUndefined();
    expect(headers["X-Requested-With"]).toBe("XMLHttpRequest");
  });

  it("handles multiple events in a single chunk", async () => {
    stubFetchWithStream(
      streamFromChunks([
        'event: foo\ndata: {"v":1}\n\nevent: foo\ndata: {"v":2}\n\nevent: foo\ndata: {"v":3}\n\ndata: [DONE]\n\n',
      ]),
    );

    const events: unknown[] = [];
    for await (const e of streamTypedEvents<{ v: number }>("/x")) {
      events.push(e);
    }

    expect(events).toEqual([{ v: 1 }, { v: 2 }, { v: 3 }]);
  });
});
