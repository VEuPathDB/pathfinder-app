import { describe, expect, it } from "vitest";

import { shouldAutoOpenReview } from "./autoOpenReview";

const FIRST_TURN = {
  hasUserMessage: true,
  conversationId: "c1",
  autoOpenedConversation: null,
  autoOpenChecked: null,
  narrowViewport: false,
};

describe("shouldAutoOpenReview", () => {
  it("opens Review on the thread's first user message", () => {
    expect(shouldAutoOpenReview(FIRST_TURN)).toBe(true);
  });

  it("leaves the rail closed on a viewport too narrow to hold it", () => {
    expect(shouldAutoOpenReview({ ...FIRST_TURN, narrowViewport: true })).toBe(false);
  });

  it("waits for the reader to say something", () => {
    expect(shouldAutoOpenReview({ ...FIRST_TURN, hasUserMessage: false })).toBe(false);
  });

  it("opens once per thread", () => {
    expect(shouldAutoOpenReview({ ...FIRST_TURN, autoOpenedConversation: "c1" })).toBe(
      false,
    );
    expect(shouldAutoOpenReview({ ...FIRST_TURN, autoOpenChecked: "c1" })).toBe(false);
  });

  it("opens for a thread the reader switched to", () => {
    expect(
      shouldAutoOpenReview({
        ...FIRST_TURN,
        autoOpenedConversation: "c0",
        autoOpenChecked: "c0",
      }),
    ).toBe(true);
  });
});
