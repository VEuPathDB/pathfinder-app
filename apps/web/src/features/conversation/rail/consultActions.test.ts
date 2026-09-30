import type { UIMessage } from "ai";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useConsultAnswersStore } from "@/state/useConsultAnswersStore";

const recordProductEvent = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/productEvents", () => ({ recordProductEvent }));

import {
  handleAdoptionAnswer,
  handleConsultSkip,
  handleConsultSubmit,
  handleProposalAnswer,
  withConsultAnswers,
} from "./consultActions";

const CONVERSATION_ID = "conv-3";

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

    handleConsultSkip(
      { id: CONVERSATION_ID, addToolApprovalResponse },
      { approvalId: "approval-7" },
    );

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

describe("an answered card", () => {
  beforeEach(() => {
    recordProductEvent.mockClear();
    useConsultAnswersStore.setState({ byApprovalId: {} });
  });

  const chat = { id: CONVERSATION_ID, addToolApprovalResponse: vi.fn() };

  it("records a submitted consult as an approved consult_user", () => {
    handleConsultSubmit(chat, { approvalId: "approval-1" }, []);

    expect(recordProductEvent.mock.calls).toEqual([
      [
        {
          event: "card_answered",
          toolName: "consult_user",
          approved: true,
          conversationId: CONVERSATION_ID,
        },
      ],
    ]);
  });

  it("records a skipped consult as a declined consult_user", () => {
    handleConsultSkip(chat, { approvalId: "approval-2" });

    expect(recordProductEvent.mock.calls).toEqual([
      [
        {
          event: "card_answered",
          toolName: "consult_user",
          approved: false,
          conversationId: CONVERSATION_ID,
        },
      ],
    ]);
  });

  it("records a proposal yes and a proposal no under propose_changes", () => {
    const pending = { approvalId: "approval-3", question: "Apply?" };

    handleProposalAnswer(chat, pending, { accepted: true, note: "" });
    handleProposalAnswer(chat, pending, { accepted: false, note: "not yet" });

    expect(recordProductEvent.mock.calls).toEqual([
      [
        {
          event: "card_answered",
          toolName: "propose_changes",
          approved: true,
          conversationId: CONVERSATION_ID,
        },
      ],
      [
        {
          event: "card_answered",
          toolName: "propose_changes",
          approved: false,
          conversationId: CONVERSATION_ID,
        },
      ],
    ]);
  });

  it("records an adoption answer under adopt_separating_strategy", () => {
    handleAdoptionAnswer(chat, "approval-4", { accepted: true, note: "" });

    expect(recordProductEvent.mock.calls).toEqual([
      [
        {
          event: "card_answered",
          toolName: "adopt_separating_strategy",
          approved: true,
          conversationId: CONVERSATION_ID,
        },
      ],
    ]);
  });
});
