import type { UIMessage } from "ai";
import { describe, expect, it } from "vitest";

import { reduceWithdrawnTurns, withdrawPrompt } from "./withdrawnPrompt";

const EARLIER: UIMessage = {
  id: "u1",
  role: "user",
  parts: [{ type: "text", text: "Which site holds P. falciparum?" }],
};
const ANSWER: UIMessage = {
  id: "a1",
  role: "assistant",
  parts: [{ type: "text", text: "PlasmoDB." }],
};
const DECLINED: UIMessage = {
  id: "u2",
  role: "user",
  parts: [
    { type: "text", text: "Describe the virulence" },
    { type: "text", text: "factors of this strain." },
  ],
};

describe("withdrawPrompt", () => {
  it("removes the named prompt and hands back its words", () => {
    expect(withdrawPrompt([EARLIER, ANSWER, DECLINED], "u2")).toEqual({
      messages: [EARLIER, ANSWER],
      text: "Describe the virulence factors of this strain.",
    });
  });

  it("leaves a thread that does not hold the prompt as it is", () => {
    const thread = [EARLIER, ANSWER];

    expect(withdrawPrompt(thread, "u9")).toEqual({ messages: thread, text: null });
  });
});

describe("reduceWithdrawnTurns", () => {
  const notice = {
    type: "data-turn-withdrawn" as const,
    data: { errorText: "The model declined this request." },
  };

  it("shows a withdrawn turn as its notice alone", () => {
    const declined: UIMessage = {
      id: "a2",
      role: "assistant",
      parts: [{ type: "reasoning", text: "thinking about it" }, notice],
    };

    expect(reduceWithdrawnTurns([EARLIER, ANSWER, declined])).toEqual([
      EARLIER,
      ANSWER,
      { ...declined, parts: [notice] },
    ]);
  });

  it("leaves a thread with no withdrawn turn as it is", () => {
    const thread = [EARLIER, ANSWER];

    expect(reduceWithdrawnTurns(thread)).toBe(thread);
  });
});
