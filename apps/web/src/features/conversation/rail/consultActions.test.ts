import type { UIMessage } from "ai";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useConsultAnswersStore } from "@/state/useConsultAnswersStore";

import { handleConsultSkip, withConsultAnswers } from "./consultActions";

function respondedConsult(approved: boolean): UIMessage {
  return {
    id: "m1",
    role: "assistant",
    parts: [
      {
        type: "tool-consult_user",
        toolCallId: "call-7",
        state: "approval-responded",
        approval: { id: "approval-7", approved },
        input: { questions: [] },
      },
    ] as UIMessage["parts"],
  };
}

describe("a skipped consult", () => {
  beforeEach(() => {
    useConsultAnswersStore.setState({ byApprovalId: {} });
  });

  it("declines the approval with no reason and records no answers", () => {
    const addToolApprovalResponse = vi.fn();

    handleConsultSkip({ addToolApprovalResponse }, { approvalId: "approval-7" });

    expect(addToolApprovalResponse.mock.calls).toEqual([
      [{ id: "approval-7", approved: false }],
    ]);
    expect(useConsultAnswersStore.getState().byApprovalId).toEqual({});
  });

  it("reaches the turn as a decline with no answers part", () => {
    const sent = withConsultAnswers([respondedConsult(false)]);

    expect(sent[0]?.parts.map((part) => part.type)).toEqual(["tool-consult_user"]);
  });

  it("leaves an answered consult carrying its answers", () => {
    const answer = {
      questionId: "q1",
      prompt: "Fold-change threshold?",
      chosenLabels: ["2-fold"],
      note: "",
    };
    useConsultAnswersStore.getState().recordAnswers("approval-7", [answer]);

    const sent = withConsultAnswers([respondedConsult(true)]);

    expect(sent[0]?.parts[1]).toEqual({
      type: "data-user-question-answers",
      data: { toolCallId: "call-7", answers: [answer] },
    });
  });
});
