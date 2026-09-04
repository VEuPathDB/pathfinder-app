// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NextRequest } from "next/server";

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

function makeReq(body: string): NextRequest {
  return new NextRequest(new URL("/api/v1/chat", "http://localhost:3000"), {
    method: "POST",
    body,
    headers: { "content-type": "application/json", cookie: "session=abc" },
  });
}

function upstreamStream(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    async start(controller) {
      for (const c of chunks) {
        await new Promise((r) => setTimeout(r, 5));
        controller.enqueue(enc.encode(c));
      }
      controller.close();
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>): Promise<string[]> {
  const out: string[] = [];
  const reader = stream.getReader();
  const dec = new TextDecoder();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    out.push(dec.decode(value, { stream: true }));
  }
  return out;
}

describe("POST /api/v1/chat", () => {
  it("forwards the request body, cookie, and Accept header to the upstream API", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(upstreamStream(["data: hi\n\n"]), {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { POST } = await import("./route");

    await POST(makeReq('{"message":"hi"}'));

    expect(fetchMock).toHaveBeenCalledOnce();
    const call = fetchMock.mock.calls[0];
    if (call === undefined) throw new Error("fetch not called");
    const [url, init] = call as unknown as [
      string,
      RequestInit & { headers: Record<string, string> },
    ];
    expect(url).toBe("http://api.test/api/v1/chat");
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"message":"hi"}');
    expect(init.headers["Cookie"]).toBe("session=abc");
    expect(init.headers["Accept"]).toBe("text/event-stream");
    expect(init.headers["Content-Type"]).toBe("application/json");
  });

  it("pipes the upstream SSE stream chunk-by-chunk without buffering", async () => {
    const chunks = ["data: a\n\n", "data: b\n\n", "data: [DONE]\n\n"];
    const fetchMock = vi.fn(
      async () =>
        new Response(upstreamStream(chunks), {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { POST } = await import("./route");

    const res = await POST(makeReq("{}"));
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("text/event-stream");
    expect(res.headers.get("Cache-Control")).toBe("no-cache, no-transform");
    expect(res.headers.get("X-Accel-Buffering")).toBe("no");
    expect(res.headers.get("x-vercel-ai-ui-message-stream")).toBe("v1");
    if (res.body === null) throw new Error("response has no body");

    const received = await collect(res.body);
    expect(received).toEqual(chunks);
  });

  it("returns upstream error body and status when upstream is not ok", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response('{"detail":"unauthorized"}', {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { POST } = await import("./route");

    const res = await POST(makeReq("{}"));
    expect(res.status).toBe(401);
    expect(res.headers.get("Content-Type")).toBe("application/json");
    expect(await res.text()).toBe('{"detail":"unauthorized"}');
  });

  it("returns 502 when the upstream fetch throws", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("ECONNREFUSED");
      }),
    );
    const { POST } = await import("./route");

    const res = await POST(makeReq("{}"));
    expect(res.status).toBe(502);
    const body = (await res.json()) as { detail: string };
    expect(body.detail).toContain("ECONNREFUSED");
  });
});

describe("Next.js config for SSE", () => {
  it("has compression disabled so SSE events are flushed per event", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
    const config = (await import("../../../../../next.config")).default;
    expect(config.compress).toBe(false);
  });
});
