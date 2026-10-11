import { type NextRequest } from "next/server";

import { getConfiguredServerApiBaseUrl } from "@/lib/config/apiBase";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const STREAM_RESPONSE_HEADERS: Record<string, string> = {
  "Content-Type": "text/event-stream",
  "Cache-Control": "no-cache, no-transform",
  "X-Accel-Buffering": "no",
  "x-vercel-ai-ui-message-stream": "v1",
};

function buildUpstreamHeaders(req: NextRequest): Record<string, string> {
  const out: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  const cookie = req.headers.get("cookie");
  if (cookie !== null) out["Cookie"] = cookie;
  const auth = req.headers.get("authorization");
  if (auth !== null) out["Authorization"] = auth;
  const xrw = req.headers.get("x-requested-with");
  if (xrw !== null) out["X-Requested-With"] = xrw;
  return out;
}

export async function POST(req: NextRequest): Promise<Response> {
  const upstreamUrl = `${getConfiguredServerApiBaseUrl()}/api/v1/chat`;

  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl, {
      method: "POST",
      headers: buildUpstreamHeaders(req),
      body: req.body,
      duplex: "half",
    } as RequestInit & { duplex: "half" });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return Response.json(
      { detail: `Upstream API unreachable: ${message}` },
      { status: 502 },
    );
  }

  if (!upstream.ok || upstream.body === null) {
    const errorBody = await upstream.text();
    return new Response(errorBody, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
      },
    });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: STREAM_RESPONSE_HEADERS,
  });
}
