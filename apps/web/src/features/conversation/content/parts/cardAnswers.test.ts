import type { UIMessage } from "ai";
import { describe, expect, it } from "vitest";

import { answeredInALaterMessage } from "./cardAnswers";

const CARD: UIMessage = { id: "m1", role: "assistant", parts: [] };
const TYPED: UIMessage = {
  id: "u2",
  role: "user",
  parts: [{ type: "text", text: "Use the default range for both searches." }],
};
const NEXT_TURN: UIMessage = { id: "m3", role: "assistant", parts: [] };

describe("answeredInALaterMessage", () => {
  it("is false while the card's message is the thread's last", () => {
    expect(answeredInALaterMessage([CARD], "m1")).toBe(false);
  });

  it("is true once the researcher sent a message after the card", () => {
    expect(answeredInALaterMessage([CARD, TYPED], "m1")).toBe(true);
    expect(answeredInALaterMessage([CARD, TYPED, NEXT_TURN], "m1")).toBe(true);
  });

  it("is false when only the assistant wrote after the card", () => {
    expect(answeredInALaterMessage([CARD, NEXT_TURN], "m1")).toBe(false);
  });

  it("is false for a message the thread does not hold", () => {
    expect(answeredInALaterMessage([CARD, TYPED], "m9")).toBe(false);
  });
});
