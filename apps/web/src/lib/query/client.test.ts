/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { QueryClient } from "@tanstack/react-query";
import { APIError } from "@/lib/api/http";
import {
  setQueryErrorHandler,
  type QueryErrorNotice,
  __makeQueryClientForTests,
} from "./client";

afterEach(() => {
  setQueryErrorHandler(null);
});

function setup(): {
  client: QueryClient;
  notices: QueryErrorNotice[];
} {
  const notices: QueryErrorNotice[] = [];
  setQueryErrorHandler((n) => notices.push(n));
  const client = __makeQueryClientForTests();
  return { client, notices };
}

async function runFailingQuery(
  client: QueryClient,
  error: unknown,
  meta?: Record<string, unknown>,
): Promise<void> {
  await client
    .fetchQuery({
      queryKey: ["test", crypto.randomUUID()],
      queryFn: () => Promise.reject(error),
      retry: false,
      ...(meta != null ? { meta } : {}),
    })
    .catch(() => {});
}

describe("global query error handler", () => {
  beforeEach(() => {
    setQueryErrorHandler(null);
  });

  it("surfaces 5xx APIErrors via the notice handler", async () => {
    const { client, notices } = setup();
    await runFailingQuery(
      client,
      new APIError("server boom", {
        status: 500,
        statusText: "Internal Server Error",
        url: "/x",
        data: null,
      }),
    );
    expect(notices).toHaveLength(1);
    expect(notices[0]!.message).toBe("server boom");
  });

  it("surfaces 4xx APIErrors via the notice handler (no silent swallow)", async () => {
    const { client, notices } = setup();
    await runFailingQuery(
      client,
      new APIError("validation failed", {
        status: 422,
        statusText: "Unprocessable Entity",
        url: "/x",
        data: null,
      }),
    );
    expect(notices).toHaveLength(1);
    expect(notices[0]!.message).toBe("validation failed");
  });

  it("surfaces non-APIError exceptions", async () => {
    const { client, notices } = setup();
    await runFailingQuery(client, new Error("network down"));
    expect(notices).toHaveLength(1);
    expect(notices[0]!.message).toBe("network down");
  });

  it("respects per-query opt-out via meta.silent", async () => {
    const { client, notices } = setup();
    await runFailingQuery(
      client,
      new APIError("validation failed", {
        status: 422,
        statusText: "Unprocessable Entity",
        url: "/x",
        data: null,
      }),
      { silent: true },
    );
    expect(notices).toHaveLength(0);
  });

  it("stays silent for a 401 that is not a VEuPathDB login refusal", async () => {
    const { client, notices } = setup();
    await runFailingQuery(
      client,
      new APIError("Unauthorized", {
        status: 401,
        statusText: "Unauthorized",
        url: "/x",
        data: {
          title: "Unauthorized",
          status: 401,
          detail: "no",
          code: "UNAUTHORIZED",
        },
      }),
    );
    expect(notices).toHaveLength(0);
  });

  it("forwards a WDK_LOGIN_REQUIRED 401 with the error so the app can open the prompt", async () => {
    const { client, notices } = setup();
    const error = new APIError("VEuPathDB login required.", {
      status: 401,
      statusText: "Unauthorized",
      url: "/api/v1/gene-sets",
      data: {
        title: "VEuPathDB login required",
        status: 401,
        detail:
          "VEuPathDB serves registered users only, and this request carried no registered VEuPathDB token.",
        code: "WDK_LOGIN_REQUIRED",
      },
    });
    await runFailingQuery(client, error);
    expect(notices).toHaveLength(1);
    expect(notices[0]!.error).toBe(error);
    expect(notices[0]!.message).toBe("VEuPathDB login required.");
  });

  it("does not call handler when none is registered", async () => {
    const handler = vi.fn();
    setQueryErrorHandler(handler);
    setQueryErrorHandler(null);
    const client = __makeQueryClientForTests();
    await runFailingQuery(client, new Error("boom"));
    expect(handler).not.toHaveBeenCalled();
  });
});
