/**
 * @vitest-environment jsdom
 */
import type { UIMessage } from "ai";
import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { useConsultAnswersStore } from "@/state/useConsultAnswersStore";

import { buildChatRequestBody } from "../../runtime/buildRequestBody";
import type { ChatHelpers } from "../../runtime/chatHelpersContext";
import { ConsultCarouselView } from "./ConsultCarousel";
import { findPendingConsult, type PendingConsult } from "./consultData";

const COMBINE_PROMPT = "How should I combine the two gene sets?";

function pendingMessage(): UIMessage {
  return {
    id: "m1",
    role: "assistant",
    parts: [
      {
        type: "tool-consult_user",
        toolCallId: "call_kQ8zvR2mTf",
        state: "approval-requested",
        approval: { id: "approval-1" },
        input: {
          questions: [
            {
              id: "combine_mode",
              kind: "single_choice",
              prompt: COMBINE_PROMPT,
              context: "Both sets come from the same organism.",
              options: [{ label: "Union" }, { label: "Intersect", recommended: true }],
              allowNotes: true,
            },
            {
              id: "anything_else",
              kind: "free_text",
              prompt: "Anything else I should know?",
              options: [],
              allowNotes: true,
            },
          ],
        },
      },
    ] as UIMessage["parts"],
  };
}

function pendingOf(message: UIMessage): PendingConsult {
  const pending = findPendingConsult(message);
  if (pending === null) throw new Error("the message carries no pending consult");
  return pending;
}

function chatStub(): ChatHelpers {
  return {
    id: "conv-1",
    messages: [],
    status: "ready",
    error: undefined,
    setMessages: () => {},
    sendMessage: async () => {},
    regenerate: async () => {},
    stop: async () => {},
    addToolResult: async () => {},
    addToolOutput: async () => {},
    addToolApprovalResponse: () => {},
    clearError: () => {},
  };
}

function renderCarousel(): void {
  render(
    <ConsultCarouselView pending={pendingOf(pendingMessage())} chat={chatStub()} />,
  );
}

describe("the consult card names its own controls", () => {
  it("names each option button by its label alone", () => {
    renderCarousel();
    expect(screen.getByRole("button", { name: "Union" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Intersect" })).toBeInTheDocument();
  });

  it("reports the chosen option as pressed", () => {
    renderCarousel();
    const union = screen.getByRole("button", { name: "Union" });
    expect(union.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(union);
    expect(
      screen.getByRole("button", { name: "Union" }).getAttribute("aria-pressed"),
    ).toBe("true");
    expect(
      screen.getByRole("button", { name: "Intersect" }).getAttribute("aria-pressed"),
    ).toBe("false");
  });

  it("holds Next shut until the single-choice question has an answer", () => {
    renderCarousel();
    const next = screen.getByTestId("consult-next");
    expect(next).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Union" }));
    expect(screen.getByTestId("consult-next")).toBeEnabled();
  });

  it("names the note field", () => {
    renderCarousel();
    expect(screen.getByRole("textbox", { name: "Add a note" })).toBeInTheDocument();
  });

  it("names a free-text answer field after its purpose", async () => {
    renderCarousel();
    fireEvent.click(screen.getByRole("button", { name: "Union" }));
    fireEvent.click(screen.getByTestId("consult-next"));
    expect(
      await screen.findByRole("textbox", { name: "Your answer" }),
    ).toBeInTheDocument();
  });
});

/** The message the SDK sends once the carousel answers the approval. */
function answeredMessage(): UIMessage {
  const message = pendingMessage();
  return {
    ...message,
    parts: [
      {
        ...message.parts[0],
        state: "approval-responded",
        approval: { id: "approval-1", approved: true },
      },
    ] as UIMessage["parts"],
  };
}

describe("the answers the carousel collects reach the turn", () => {
  beforeEach(() => {
    useConsultAnswersStore.setState({ byApprovalId: {} });
  });

  it("carries every answer on the request body built in the submit's own tick", async () => {
    render(
      <ConsultCarouselView pending={pendingOf(pendingMessage())} chat={chatStub()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Union" }));
    fireEvent.click(screen.getByTestId("consult-next"));
    fireEvent.change(await screen.findByRole("textbox", { name: "Your answer" }), {
      target: { value: "nothing else" },
    });
    fireEvent.click(screen.getByTestId("consult-submit"));

    const body = buildChatRequestBody({
      conversationId: "conv-1",
      siteId: "plasmodb",
      id: "conv-1",
      trigger: "submit-message",
      messages: [answeredMessage()],
      baseBody: undefined,
    });
    expect(body.messages[0]?.parts[1]).toEqual({
      type: "data-user-question-answers",
      data: {
        toolCallId: "call_kQ8zvR2mTf",
        answers: [
          {
            questionId: "combine_mode",
            prompt: COMBINE_PROMPT,
            chosenLabels: ["Union"],
            note: "",
          },
          {
            questionId: "anything_else",
            prompt: "Anything else I should know?",
            chosenLabels: [],
            note: "nothing else",
          },
        ],
      },
    });
  });
});
