import type { UIMessage } from "ai";
import { describe, expect, it } from "vitest";

import { answeredInALaterMessage, isOpenCard, openCards } from "./cardAnswers";

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

const TWO_ASKED: UIMessage = {
  id: "m1",
  role: "assistant",
  parts: [
    { type: "text", text: "Remove the orthology step?" },
    {
      type: "tool-delete_step",
      toolCallId: "call_delete",
      state: "approval-requested",
      input: { step_id: "s2" },
      approval: { id: "approval-delete" },
    },
    {
      type: "tool-consult_user",
      toolCallId: "call_consult",
      state: "approval-requested",
      input: { questions: [] },
      approval: { id: "approval-consult" },
    },
  ],
};

const DELETE_ANSWERED: UIMessage = {
  id: "m1",
  role: "assistant",
  parts: [
    {
      type: "tool-delete_step",
      toolCallId: "call_delete",
      state: "approval-responded",
      input: { step_id: "s2" },
      approval: { id: "approval-delete", approved: true },
    },
  ],
};

describe("openCards", () => {
  it("lists each call that waits on the researcher, in thread order", () => {
    expect(openCards([TWO_ASKED])).toEqual([
      {
        messageId: "m1",
        toolCallId: "call_delete",
        toolName: "delete_step",
        approvalId: "approval-delete",
        input: { step_id: "s2" },
      },
      {
        messageId: "m1",
        toolCallId: "call_consult",
        toolName: "consult_user",
        approvalId: "approval-consult",
        input: { questions: [] },
      },
    ]);
  });

  it("lists no card the researcher answered with a click", () => {
    expect(openCards([DELETE_ANSWERED])).toEqual([]);
  });

  it("lists no card the researcher answered by typing", () => {
    expect(openCards([TWO_ASKED, TYPED])).toEqual([]);
  });

  it("keeps a card open while only the assistant wrote after it", () => {
    expect(openCards([TWO_ASKED, NEXT_TURN]).map((card) => card.toolCallId)).toEqual([
      "call_delete",
      "call_consult",
    ]);
  });
});

describe("isOpenCard", () => {
  it("is true for a call that waits on the researcher", () => {
    expect(isOpenCard([TWO_ASKED], "call_delete")).toBe(true);
  });

  it("is false once the call is answered", () => {
    expect(isOpenCard([DELETE_ANSWERED], "call_delete")).toBe(false);
    expect(isOpenCard([TWO_ASKED, TYPED], "call_delete")).toBe(false);
  });

  it("is false for a call the thread does not hold", () => {
    expect(isOpenCard([TWO_ASKED], "call_other")).toBe(false);
  });
});
