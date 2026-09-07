import { describe, expect, it } from "vitest";

import { shouldAutoOpenLedger } from "./autoOpenLedger";

const FIRST_TURN = {
  hasUserMessage: true,
  conversationId: "c1",
  autoOpenedConversation: null,
  autoOpenChecked: null,
  narrowViewport: false,
};

describe("shouldAutoOpenLedger", () => {
  it("opens the ledger on the thread's first user message", () => {
    expect(shouldAutoOpenLedger(FIRST_TURN)).toBe(true);
  });

  it("leaves the rail closed on a viewport too narrow to hold it", () => {
    expect(shouldAutoOpenLedger({ ...FIRST_TURN, narrowViewport: true })).toBe(false);
  });

  it("waits for the reader to say something", () => {
    expect(shouldAutoOpenLedger({ ...FIRST_TURN, hasUserMessage: false })).toBe(false);
  });

  it("opens once per thread", () => {
    expect(shouldAutoOpenLedger({ ...FIRST_TURN, autoOpenedConversation: "c1" })).toBe(
      false,
    );
    expect(shouldAutoOpenLedger({ ...FIRST_TURN, autoOpenChecked: "c1" })).toBe(false);
  });

  it("opens for a thread the reader switched to", () => {
    expect(
      shouldAutoOpenLedger({
        ...FIRST_TURN,
        autoOpenedConversation: "c0",
        autoOpenChecked: "c0",
      }),
    ).toBe(true);
  });
});
