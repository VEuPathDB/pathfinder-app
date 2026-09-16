import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { z } from "zod";

import { MISSING_API_URL_MESSAGE } from "@/lib/config/apiBase";

import { APIError, buildUrl, getAuthHeaders, requestJson, requestVoid } from "./http";

function makeHeaders(init: Record<string, string>) {
  const normalized = new Map<string, string>();
  for (const [k, v] of Object.entries(init)) normalized.set(k.toLowerCase(), v);
  return {
    get(name: string) {
      return normalized.get(name.toLowerCase()) ?? null;
    },
  } as Headers;
}

function makeResponse(args: {
  ok: boolean;
  status: number;
  statusText: string;
  headers?: Record<string, string>;
  json?: unknown;
  text?: string;
}): Response {
  const headers = makeHeaders(args.headers ?? {});
  return {
    ok: args.ok,
    status: args.status,
    statusText: args.statusText,
    headers,
    async json() {
      return args.json;
    },
    async text() {
      return args.text ?? "";
    },
  } as unknown as Response;
}

describe("lib/api/http", () => {
  const ORIGINAL_ENV = { ...process.env };

  beforeEach(() => {
    process.env = { ...ORIGINAL_ENV };
  });

  afterEach(() => {
    process.env = { ...ORIGINAL_ENV };
    vi.unstubAllGlobals();
  });

  it("buildUrl uses NEXT_PUBLIC_API_URL and encodes query params", () => {
    process.env["NEXT_PUBLIC_API_URL"] = "http://localhost:8000///";
    const url = buildUrl("/api/v1/sites", {
      siteId: "plasmodb",
      recordType: "gene",
      n: 2,
      ok: true,
      skip: null,
      missing: undefined,
    });
    expect(url).toBe(
      "http://localhost:8000/api/v1/sites?siteId=plasmodb&recordType=gene&n=2&ok=true",
    );
  });

  it("buildUrl throws when NEXT_PUBLIC_API_URL is missing on the server", () => {
    delete process.env["NEXT_PUBLIC_API_URL"];
    expect(() => buildUrl("/api/v1/sites")).toThrow(MISSING_API_URL_MESSAGE);
  });

  it("getAuthHeaders includes optional accept/content-type", () => {
    const headers = getAuthHeaders({
      accept: "application/json",
      contentType: "application/json",
      extra: { "x-test": "1" },
    });
    expect(headers["Accept"]).toBe("application/json");
    expect(headers["Content-Type"]).toBe("application/json");
    expect(headers["x-test"]).toBe("1");
    // Auth is handled via httpOnly cookies - no Authorization header
    expect(headers["Authorization"]).toBeUndefined();
  });

  it("requestJson validates response against schema", async () => {
    process.env["NEXT_PUBLIC_API_URL"] = "http://localhost:8000";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        makeResponse({
          ok: true,
          status: 200,
          statusText: "OK",
          headers: { "content-type": "application/json" },
          json: { hello: "world" },
        }),
      ),
    );

    const schema = z.object({ hello: z.string() });
    const data = await requestJson(schema, "/api/v1/health");
    expect(data).toEqual({ hello: "world" });
  });

  it("requestJson throws SchemaValidationError on invalid response", async () => {
    process.env["NEXT_PUBLIC_API_URL"] = "http://localhost:8000";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        makeResponse({
          ok: true,
          status: 200,
          statusText: "OK",
          headers: { "content-type": "application/json" },
          json: { hello: 42 },
        }),
      ),
    );

    const schema = z.object({ hello: z.string() });
    await expect(requestJson(schema, "/api/v1/health")).rejects.toThrow(
      "validation failed",
    );
  });

  it("requestJson throws APIError with server 'detail' message", async () => {
    process.env["NEXT_PUBLIC_API_URL"] = "http://localhost:8000";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        makeResponse({
          ok: false,
          status: 401,
          statusText: "Unauthorized",
          headers: { "content-type": "application/json" },
          json: { detail: "No auth" },
        }),
      ),
    );

    await expect(requestJson(z.unknown(), "/api/v1/private")).rejects.toMatchObject({
      name: "APIError",
      message: "No auth",
      status: 401,
    });
  });

  it("requestJson throws APIError with generic message when no JSON detail", async () => {
    process.env["NEXT_PUBLIC_API_URL"] = "http://localhost:8000";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        makeResponse({
          ok: false,
          status: 500,
          statusText: "Internal Server Error",
          headers: { "content-type": "text/plain" },
          text: "nope",
        }),
      ),
    );

    try {
      await requestJson(z.unknown(), "/api/v1/broken");
      expect.unreachable();
    } catch (e) {
      expect(e).toBeInstanceOf(APIError);
      expect((e as APIError).message).toBe("HTTP 500 Internal Server Error");
      expect((e as APIError).status).toBe(500);
      expect((e as APIError).url).toContain("/api/v1/broken");
    }
  });

  it("requestVoid resolves on success", async () => {
    process.env["NEXT_PUBLIC_API_URL"] = "http://localhost:8000";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        makeResponse({ ok: true, status: 204, statusText: "No Content", headers: {} }),
      ),
    );
    await expect(
      requestVoid("/api/v1/thing", { method: "DELETE" }),
    ).resolves.toBeUndefined();
  });

  it("requestVoid throws APIError on failure", async () => {
    process.env["NEXT_PUBLIC_API_URL"] = "http://localhost:8000";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        makeResponse({
          ok: false,
          status: 404,
          statusText: "Not Found",
          headers: { "content-type": "application/json" },
          json: { detail: "Not found" },
        }),
      ),
    );
    await expect(
      requestVoid("/api/v1/missing", { method: "DELETE" }),
    ).rejects.toMatchObject({
      name: "APIError",
      message: "Not found",
      status: 404,
    });
  });
});

describe("a refused request reports the server's message", () => {
  beforeEach(() => {
    process.env["NEXT_PUBLIC_API_URL"] = "http://localhost:8000";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function refuse(body: unknown, status = 422, statusText = "Unprocessable Content") {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        makeResponse({
          ok: false,
          status,
          statusText,
          headers: { "content-type": "application/problem+json" },
          json: body,
        }),
      ),
    );
  }

  it("names the field a plan validation refused, not the HTTP status", async () => {
    refuse({
      type: "about:blank",
      title: "Invalid plan",
      status: 422,
      code: "VALIDATION_ERROR",
      errors: [
        { path: "recordType", message: "Record type is required", code: "REQUIRED" },
      ],
    });
    const error = await requestJson(z.object({}), "/api/v1/conversations/step-counts", {
      method: "POST",
      body: {},
    }).catch((err: unknown) => err);
    expect(error).toBeInstanceOf(APIError);
    expect((error as APIError).message).toBe("Record type is required");
  });

  it("joins every field message a refusal carries", async () => {
    refuse({
      title: "Invalid plan",
      status: 422,
      code: "VALIDATION_ERROR",
      errors: [
        { path: "recordType", message: "Record type is required", code: "REQUIRED" },
        { path: "root", message: "A strategy needs one step", code: "EMPTY" },
      ],
    });
    const error = await requestJson(z.object({}), "/api/v1/conversations/step-counts", {
      method: "POST",
      body: {},
    }).catch((err: unknown) => err);
    expect((error as APIError).message).toBe(
      "Record type is required; A strategy needs one step",
    );
  });

  it("falls back to the problem title when the body carries no field message", async () => {
    refuse({
      title: "Enrichment analysis failed",
      status: 500,
      code: "INTERNAL_ERROR",
    });
    const error = await requestJson(z.object({}), "/api/v1/gene-sets/x/enrich", {
      method: "POST",
      body: {},
    }).catch((err: unknown) => err);
    expect((error as APIError).message).toBe("Enrichment analysis failed");
  });

  it("keeps the transport line when the body says nothing", async () => {
    refuse(null, 502, "Bad Gateway");
    const error = await requestJson(z.object({}), "/api/v1/gene-sets").catch(
      (err: unknown) => err,
    );
    expect((error as APIError).message).toBe("HTTP 502 Bad Gateway");
  });
});
