import type { UIMessage } from "ai";
import { describe, expect, it } from "vitest";

import { findConsultRecap, findPendingConsult, findProposal } from "./consultData";

function assistant(parts: UIMessage["parts"]): UIMessage {
  return { id: "m1", role: "assistant", parts };
}

describe("findPendingConsult", () => {
  it("reads questions off a pending consult_user approval part", () => {
    const message = assistant([
      {
        type: "tool-consult_user",
        toolCallId: "call-1",
        state: "approval-requested",
        approval: { id: "appr-9" },
        input: {
          questions: [
            {
              id: "q1",
              prompt: "Fold-change threshold?",
              kind: "single_choice",
              options: [{ label: "2-fold", recommended: true }, { label: "5-fold" }],
              context: "Higher is stricter.",
              allowNotes: true,
            },
          ],
        },
      },
    ]);
    const pending = findPendingConsult(message);
    expect(pending?.approvalId).toBe("appr-9");
    expect(pending?.questions).toHaveLength(1);
    expect(pending?.questions[0]?.prompt).toBe("Fold-change threshold?");
    expect(pending?.questions[0]?.options?.[0]?.recommended).toBe(true);
  });

  it("returns null when there is no pending consult", () => {
    expect(findPendingConsult(assistant([{ type: "text", text: "hi" }]))).toBe(null);
  });

  it("drops a question the tool input did not fill, instead of showing a blank slide", () => {
    const message = assistant([
      {
        type: "tool-consult_user",
        toolCallId: "call-1",
        state: "approval-requested",
        approval: { id: "appr-9" },
        input: { questions: [{ id: "q1" }, { id: "q2", prompt: "Threshold?" }] },
      },
    ]);
    expect(findPendingConsult(message)?.questions).toEqual([
      {
        id: "q2",
        prompt: "Threshold?",
        kind: "single_choice",
        context: "",
        allowNotes: true,
      },
    ]);
  });
});

describe("findConsultRecap", () => {
  it("reads questions + chosen answers from a resolved consult tool part", () => {
    const message = assistant([
      {
        type: "tool-consult_user",
        toolCallId: "call-1",
        state: "output-available",
        input: {
          questions: [
            { id: "q1", prompt: "Threshold?", options: [{ label: "2-fold" }] },
          ],
        },
        output: [
          {
            questionId: "q1",
            prompt: "Threshold?",
            chosenLabels: ["2-fold"],
            note: "",
          },
        ],
      },
    ]);
    const recap = findConsultRecap(message);
    expect(recap?.questions[0]?.prompt).toBe("Threshold?");
    expect(recap?.answers[0]?.chosenLabels).toEqual(["2-fold"]);
  });

  it("drops an answer that names no question", () => {
    const message = assistant([
      {
        type: "tool-consult_user",
        toolCallId: "call-1",
        state: "output-available",
        input: { questions: [{ id: "q1", prompt: "Threshold?" }] },
        output: [{ prompt: "Threshold?", chosenLabels: ["2-fold"] }],
      },
    ]);
    expect(findConsultRecap(message)?.answers).toEqual([]);
  });

  it("returns null when the consult is still pending", () => {
    const message = assistant([
      {
        type: "tool-consult_user",
        toolCallId: "call-1",
        state: "approval-requested",
        approval: { id: "a" },
        input: { questions: [] },
      },
    ]);
    expect(findConsultRecap(message)).toBe(null);
  });
});

describe("findProposal", () => {
  it("reads the card off the arguments propose_changes advertises", () => {
    // pydantic-ai flattens the one model argument, so the fields sit at the top.
    const message = assistant([
      {
        type: "tool-propose_changes",
        toolCallId: "call-7",
        state: "approval-requested",
        approval: { id: "appr-7" },
        input: {
          reply: "One change would make this strategy more specific.",
          question: "Add one more search to make this strategy more specific?",
          proposedChanges: ["Keep only the genes another search of the site returns"],
        },
      },
    ]);

    expect(findProposal(message, "call-7")).toEqual({
      proposal: {
        question: "Add one more search to make this strategy more specific?",
        proposedChanges: ["Keep only the genes another search of the site returns"],
      },
      decision: "pending",
      approvalId: "appr-7",
    });
  });
});
