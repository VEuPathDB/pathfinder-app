import { describe, expect, it } from "vitest";

import { isServerMessageId } from "./messageIds";

describe("isServerMessageId", () => {
  it("accepts the UUID the server writes", () => {
    expect(isServerMessageId("791b00a6-b23a-4874-ab25-9caa90470d2d")).toBe(true);
  });

  it("refuses an id the client made up", () => {
    expect(
      ["a_zuWkLc3Pq1", "msg_1", "__optimistic__x", ""].map(isServerMessageId),
    ).toEqual([false, false, false, false]);
  });
});
