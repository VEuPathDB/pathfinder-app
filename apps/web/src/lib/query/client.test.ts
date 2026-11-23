/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { QueryClient, QueryMeta } from "@tanstack/react-query";
import { APIError } from "@/lib/api/http";
import { AppError } from "@/lib/errors/AppError";
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
  meta?: QueryMeta,
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

  it("drops a WDK_LOGIN_REQUIRED 401 on a silent query", async () => {
    const { client, notices } = setup();
    const error = new APIError("VEuPathDB login required.", {
      status: 401,
      statusText: "Unauthorized",
      url: "/api/v1/sites/plasmodb/searches",
      data: {
        title: "VEuPathDB login required",
        status: 401,
        detail:
          "VEuPathDB serves registered users only, and this request carried no registered VEuPathDB token.",
        code: "WDK_LOGIN_REQUIRED",
      },
    });
    await runFailingQuery(client, error, { silent: true });
    expect(notices).toHaveLength(0);
  });

  it("sends no notice for a query whose component shows the error itself", async () => {
    const { client, notices } = setup();
    await runFailingQuery(
      client,
      new APIError("figure read failed", {
        status: 500,
        statusText: "Internal Server Error",
        url: "/api/v1/eda/viz?siteId=plasmodb&conversationId=conv-1",
        data: null,
      }),
      { shownInline: true },
    );
    expect(notices).toHaveLength(0);
  });

  it("forwards a WDK_LOGIN_REQUIRED 401 on a query whose component shows the error itself", async () => {
    const { client, notices } = setup();
    const error = new APIError("VEuPathDB login required.", {
      status: 401,
      statusText: "Unauthorized",
      url: "/api/v1/eda/viz",
      data: {
        title: "VEuPathDB login required",
        status: 401,
        detail:
          "VEuPathDB serves registered users only, and this request carried no registered VEuPathDB token.",
        code: "WDK_LOGIN_REQUIRED",
      },
    });
    await runFailingQuery(client, error, { shownInline: true });
    expect(notices).toHaveLength(1);
    expect(notices[0]!.error).toBe(error);
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

describe("default retry policy", () => {
  function retries(error: Error): boolean {
    const retry = __makeQueryClientForTests().getDefaultOptions().queries?.retry;
    if (typeof retry !== "function") throw new Error("retry is not a policy");
    return retry(0, error);
  }

  it("does not repeat a request that timed out", () => {
    expect(retries(new AppError("no answer", "TIMEOUT"))).toBe(false);
  });

  it("does not repeat a request the api refused because the site is down", () => {
    const refusal = new APIError("Could not connect to plasmodb (ReadTimeout).", {
      status: 503,
      statusText: "Service Unavailable",
      url: "/api/v1/veupathdb/auth/status",
      data: {
        status: 503,
        detail: "Could not connect to plasmodb (ReadTimeout).",
        code: "SITE_UNAVAILABLE",
      },
    });
    expect(retries(refusal)).toBe(false);
  });

  it("repeats a request the network dropped", () => {
    expect(retries(new Error("network down"))).toBe(true);
  });
});
