/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppError } from "@/lib/errors/AppError";
import { getVeupathdbAuthStatus } from "./veupathdb-auth";

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
