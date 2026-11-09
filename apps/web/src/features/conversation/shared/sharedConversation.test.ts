import { describe, expect, it } from "vitest";

import { APIError } from "@/lib/api/http";

import {
  SHARED_POLL_MS,
  sharedPollAfter,
  sharedRefusalOf,
  sharedRetry,
} from "./sharedConversation";

function refusal(status: number, code: string): APIError {
  return new APIError("refused", {
    status,
    statusText: "",
    url: "/api/v1/shared/tok-1",
    data: { title: "refused", status, code },
  });
}

const GONE = refusal(404, "SHARE_NOT_FOUND");
const LOCKED = refusal(403, "SHARE_LOCKED");
const DOWN = refusal(502, "INTERNAL_ERROR");

describe("sharedRefusalOf", () => {
  it.each([
    [GONE, "gone"],
    [LOCKED, "locked"],
    [DOWN, "failed"],
    [new TypeError("network"), "failed"],
  ])("reads %s as %s", (error, expected) => {
    expect(sharedRefusalOf(error)).toBe(expected);
  });
});

describe("sharedRetry", () => {
  it("retries a failed read twice", () => {
    expect([0, 1, 2].map((count) => sharedRetry(count, DOWN))).toEqual([
      true,
      true,
      false,
    ]);
  });

  it("never retries a link that is gone or locked", () => {
    expect([sharedRetry(0, GONE), sharedRetry(0, LOCKED)]).toEqual([false, false]);
  });
});

describe("sharedPollAfter", () => {
  it("keeps polling after a read that failed", () => {
    expect(sharedPollAfter(DOWN)).toBe(SHARED_POLL_MS);
    expect(sharedPollAfter(null)).toBe(SHARED_POLL_MS);
  });

  it("stops polling a link that is gone or locked", () => {
    expect([sharedPollAfter(GONE), sharedPollAfter(LOCKED)]).toEqual([false, false]);
  });
});
