import type { UIMessage } from "ai";
import { beforeEach, describe, it, expect } from "vitest";

import { useConsultAnswersStore } from "@/state/useConsultAnswersStore";

import { buildChatRequestBody } from "./buildRequestBody";

describe("buildChatRequestBody", () => {
  it("throws if siteId is empty", () => {
    expect(() =>
      buildChatRequestBody({
        conversationId: "c1",
        siteId: "",
        id: "x",
        trigger: "submit-message",
        messages: [],
        baseBody: undefined,
      }),
    ).toThrow(/siteId is required/);
  });

  it("throws if siteId is whitespace only", () => {
    expect(() =>
      buildChatRequestBody({
        conversationId: "c1",
        siteId: "   ",
        id: "x",
        trigger: "submit-message",
        messages: [],
        baseBody: undefined,
      }),
    ).toThrow();
  });

  it("includes siteId, conversationId, id, trigger, messages when siteId is set", () => {
    const out = buildChatRequestBody({
      conversationId: "c1",
      siteId: "plasmodb",
      id: "x",
      trigger: "submit-message",
      messages: [],
      baseBody: undefined,
    });
    expect(out).toMatchObject({
      conversationId: "c1",
      siteId: "plasmodb",
      id: "x",
      trigger: "submit-message",
      messages: [],
    });
  });

  it("merges base body fields under our overrides", () => {
    const out = buildChatRequestBody({
      conversationId: "c1",
      siteId: "plasmodb",
      id: "x",
      trigger: "submit-message",
      messages: [],
      baseBody: { extra: "passthrough", conversationId: "should-be-overridden" },
    });
    expect(out["extra"]).toBe("passthrough");
    expect(out.conversationId).toBe("c1");
  });

  it("includes phaseModels and phaseReasoning when non-empty", () => {
    const out = buildChatRequestBody({
      conversationId: "c1",
      siteId: "plasmodb",
      id: "x",
      trigger: "submit-message",
      messages: [],
      baseBody: undefined,
      phaseModels: { lead: "openai:gpt-5.4", frame: "anthropic:claude-sonnet-4-6" },
      phaseReasoning: { lead: "high" },
    });
    expect(out["phaseModels"]).toEqual({
      lead: "openai:gpt-5.4",
      frame: "anthropic:claude-sonnet-4-6",
    });
    expect(out["phaseReasoning"]).toEqual({ lead: "high" });
  });

  it("names the assistant when the caller gives one", () => {
    const out = buildChatRequestBody({
      conversationId: "c1",
      siteId: "plasmodb",
      id: "x",
      trigger: "submit-message",
      messages: [],
      baseBody: undefined,
      assistantId: "site_help",
    });
    expect(out["assistantId"]).toBe("site_help");
  });

  it("omits the assistant when the caller names none", () => {
    const out = buildChatRequestBody({
      conversationId: "c1",
      siteId: "plasmodb",
      id: "x",
      trigger: "submit-message",
      messages: [],
      baseBody: undefined,
    });
    expect("assistantId" in out).toBe(false);
  });

  it("omits phaseModels and phaseReasoning when empty or missing", () => {
    const out = buildChatRequestBody({
      conversationId: "c1",
      siteId: "plasmodb",
      id: "x",
      trigger: "submit-message",
      messages: [],
      baseBody: undefined,
      phaseModels: {},
      phaseReasoning: {},
    });
    expect("phaseModels" in out).toBe(false);
    expect("phaseReasoning" in out).toBe(false);
  });
});

function answeredConsult(): UIMessage {
  return {
    id: "m1",
    role: "assistant",
    parts: [
      {
        type: "tool-consult_user",
        toolCallId: "call-7",
        state: "approval-responded",
        approval: { id: "approval-7", approved: true },
        input: { questions: [] },
      },
    ] as UIMessage["parts"],
  };
}

const ANSWER = {
  questionId: "q1",
  prompt: "Fold-change threshold?",
  chosenLabels: ["2-fold"],
  note: "",
};

describe("the answers an approved consult carries", () => {
  beforeEach(() => {
    useConsultAnswersStore.setState({ byApprovalId: {} });
  });

  it("rides the message that answers the approval, keyed by its tool call", () => {
    useConsultAnswersStore.getState().recordAnswers("approval-7", [ANSWER]);
    const out = buildChatRequestBody({
      conversationId: "c1",
      siteId: "plasmodb",
      id: "x",
      trigger: "submit-message",
      messages: [answeredConsult()],
      baseBody: undefined,
    });
    expect(out.messages[0]?.parts[1]).toEqual({
      type: "data-user-question-answers",
      data: { toolCallId: "call-7", answers: [ANSWER] },
    });
  });

  it("refuses a send whose answered consult it never recorded", () => {
    expect(() =>
      buildChatRequestBody({
        conversationId: "c1",
        siteId: "plasmodb",
        id: "x",
        trigger: "submit-message",
        messages: [answeredConsult()],
        baseBody: undefined,
      }),
    ).toThrow(/approval-7/);
  });

  it("leaves another tool's answered approval alone", () => {
    const message: UIMessage = {
      id: "m2",
      role: "assistant",
      parts: [
        {
          type: "tool-delete_step",
          toolCallId: "call-9",
          state: "approval-responded",
          approval: { id: "approval-9", approved: true },
          input: { stepId: 3 },
        },
      ] as UIMessage["parts"],
    };
    const out = buildChatRequestBody({
      conversationId: "c1",
      siteId: "plasmodb",
      id: "x",
      trigger: "submit-message",
      messages: [message],
      baseBody: undefined,
    });
    expect(out.messages[0]?.parts).toHaveLength(1);
  });

  it("leaves a message that answers nothing alone", () => {
    const plain: UIMessage = {
      id: "m0",
      role: "user",
      parts: [{ type: "text", text: "hello" }],
    };
    const out = buildChatRequestBody({
      conversationId: "c1",
      siteId: "plasmodb",
      id: "x",
      trigger: "submit-message",
      messages: [plain],
      baseBody: undefined,
    });
    expect(out.messages).toEqual([plain]);
  });
});

describe("the files a turn carries", () => {
  const png = {
    type: "file" as const,
    mediaType: "image/png",
    filename: "table.png",
    url: "data:image/png;base64,iVBORw0KGgo=",
  };

  it("keeps the files of the message being sent and drops those of earlier ones", () => {
    const out = buildChatRequestBody({
      conversationId: "c1",
      siteId: "plasmodb",
      id: "x",
      trigger: "submit-message",
      messages: [
        { id: "u1", role: "user", parts: [{ type: "text", text: "first" }, png] },
        { id: "a1", role: "assistant", parts: [{ type: "text", text: "seen" }] },
        { id: "u2", role: "user", parts: [{ type: "text", text: "second" }, png] },
      ],
      baseBody: undefined,
    });
    expect(out.messages.map((m) => m.parts.map((p) => p.type))).toEqual([
      ["text"],
      ["text"],
      ["text", "file"],
    ]);
  });
});
