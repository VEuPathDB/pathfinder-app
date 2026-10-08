/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppError } from "@/lib/errors/AppError";
import { createTestQueryClient } from "@/lib/query/testing";
import {
  authRefreshOptions,
  authStatusOptions,
  getVeupathdbAuthStatus,
} from "./veupathdb-auth";

function fetchThatNeverAnswers() {
  return vi.fn(
    (_url: string, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(init.signal?.reason));
      }),
  );
}

/** jsdom arms AbortSignal.timeout on its own window timer, which fake timers do not drive. */
function timeoutOnFakeTimers(ms: number): AbortSignal {
  const controller = new AbortController();
  setTimeout(() => controller.abort(new DOMException("timed out", "TimeoutError")), ms);
  return controller.signal;
}

describe("getVeupathdbAuthStatus", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(AbortSignal, "timeout").mockImplementation(timeoutOnFakeTimers);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("fails with a timeout once the sign-in check has not answered in 15 s", async () => {
    vi.stubGlobal("fetch", fetchThatNeverAnswers());
    let settled: unknown = "pending";
    const status = getVeupathdbAuthStatus("plasmodb").then(
      () => "resolved",
      (error: unknown) => error,
    );
    void status.then((value) => {
      settled = value;
    });

    await vi.advanceTimersByTimeAsync(14_999);
    expect(settled).toBe("pending");

    await vi.advanceTimersByTimeAsync(1);
    const error = await status;
    expect(error).toBeInstanceOf(AppError);
    expect(error).toMatchObject({ code: "TIMEOUT" });
  });
});

describe("authStatusOptions", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("aborts a cancelled status read before it can drop the refresh", async () => {
    const signals: (AbortSignal | null | undefined)[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init?: RequestInit) => {
        signals.push(init?.signal);
        return new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(init.signal?.reason));
        });
      }),
    );
    const client = createTestQueryClient();
    const refresh = authRefreshOptions("plasmodb").queryKey;
    client.setQueryData(refresh, { refreshed: true });
    const status = authStatusOptions("plasmodb");

    const read = client.fetchQuery(status).catch(() => null);
    await vi.waitFor(() => expect(signals).toHaveLength(1));
    await client.cancelQueries({ queryKey: status.queryKey });
    await read;

    expect(signals[0]?.aborted).toBe(true);
    expect(client.getQueryData(refresh)).toEqual({ refreshed: true });
  });
});
