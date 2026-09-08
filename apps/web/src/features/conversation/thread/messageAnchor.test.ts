import { describe, expect, it } from "vitest";

import { messageAnchorId } from "./messageAnchor";

describe("messageAnchorId", () => {
  it("names the message's own anchor", () => {
    expect(messageAnchorId("a2bebd4e")).toBe("message-a2bebd4e");
  });
});
