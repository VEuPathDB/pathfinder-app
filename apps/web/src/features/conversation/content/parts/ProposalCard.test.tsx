/**
 * @vitest-environment jsdom
 */
import { useChat } from "@ai-sdk/react";
import {
  lastAssistantMessageIsCompleteWithApprovalResponses,
  type ChatTransport,
  type UIMessage,
  type UIMessageChunk,
} from "ai";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { useConsultAnswersStore } from "@/state/useConsultAnswersStore";

import { buildChatRequestBody } from "../../runtime/buildRequestBody";
import {
  ChatHelpersProvider,
  type ChatHelpers,
} from "../../runtime/chatHelpersContext";
import { findProposal } from "./consultData";

vi.mock("@assistant-ui/react", () => ({
  useAuiState: (select: (s: { message: { id: string } }) => unknown) =>
    select({ message: { id: "m1" } }),
}));

import { ProposalCard } from "./ProposalCard";

const CALL_ID = "call_propose_changes";
const QUESTION =
  "Refine the strategy to enforce strict 3-hour specificity and require 1:1:1 syntenic orthologs?";
const CHANGES = [
  "Exclude genes highly expressed at the other post-blood-meal time points",
  "Require 1:1:1 syntenic orthologs in Aedes aegypti and Culex quinquefasciatus",
];

type Part = UIMessage["parts"][number];

const CARD = {
  type: "tool-propose_changes",
  toolCallId: CALL_ID,
  input: { question: QUESTION, proposedChanges: CHANGES },
} as const;

const PENDING: Part = {
  ...CARD,
  state: "approval-requested",
  approval: { id: "approval-7" },
};

function responded(approved: boolean): Part {
  return {
    ...CARD,
    state: "approval-responded",
    approval: { id: "approval-7", approved },
  };
}

function message(part: Part): UIMessage {
  return { id: "m1", role: "assistant", parts: [part] };
}

type Response = Parameters<ChatHelpers["addToolApprovalResponse"]>[0];

function chatStub(part: Part, responses: Response[]): ChatHelpers {
  return {
    id: "conv-1",
    messages: [message(part)],
    status: "ready",
    error: undefined,
    setMessages: () => {},
    sendMessage: async () => {},
    regenerate: async () => {},
    stop: async () => {},
    addToolResult: async () => {},
    addToolOutput: async () => {},
    addToolApprovalResponse: (response) => {
      responses.push(response);
    },
    clearError: () => {},
  };
}

function renderCard(part: Part, responses: Response[] = []): void {
  render(
    <ChatHelpersProvider value={chatStub(part, responses)}>
      <ProposalCard toolCallId={CALL_ID} />
    </ChatHelpersProvider>,
  );
}

function openTurn(): ChatTransport<UIMessage>["sendMessages"] {
  return vi.fn(async () => new ReadableStream<UIMessageChunk>());
}

function LiveThread({
  sendMessages,
}: {
  sendMessages: ChatTransport<UIMessage>["sendMessages"];
}) {
  const chat = useChat({
    id: "conv-1",
    messages: [message(PENDING)],
    transport: { sendMessages, reconnectToStream: async () => null },
    sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithApprovalResponses,
  });
  return (
    <ChatHelpersProvider value={chat}>
      <ProposalCard toolCallId={CALL_ID} />
    </ChatHelpersProvider>
  );
}

beforeEach(() => {
  useConsultAnswersStore.setState({ byApprovalId: {} });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the proposal card shows the offer", () => {
  it("renders the question, each proposed change and both answers", () => {
    renderCard(PENDING);
    expect(screen.getByTestId("proposal-question")).toHaveTextContent(QUESTION);
    const changes = within(screen.getByRole("list", { name: "Proposed changes" }))
      .getAllByRole("listitem")
      .map((item) => item.textContent);
    expect(changes).toEqual(CHANGES);
    expect(screen.getByRole("button", { name: "Yes" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "No" })).toBeEnabled();
    expect(screen.getByRole("textbox", { name: "Add a note" })).toBeInTheDocument();
  });

  it("renders two identical changes as two items under distinct keys", () => {
    const logged = vi.spyOn(console, "error").mockImplementation(() => {});
    const change = "Require 1:1:1 syntenic orthologs in all three species";
    renderCard({
      ...PENDING,
      input: { question: QUESTION, proposedChanges: [change, change] },
    });
    const changes = within(screen.getByRole("list", { name: "Proposed changes" }))
      .getAllByRole("listitem")
      .map((item) => item.textContent);
    expect(changes).toEqual([change, change]);
    expect(logged.mock.calls.flat().join(" ")).not.toContain("same key");
  });

  it("shows the answer instead of the buttons once the card is declined", () => {
    renderCard({
      ...CARD,
      state: "output-denied",
      approval: { id: "approval-7", approved: false },
    });
    expect(screen.getByTestId("proposal-decision")).toHaveTextContent("You said no.");
    expect(screen.queryByRole("button", { name: "Yes" })).not.toBeInTheDocument();
  });

  it("shows the answer once the accepted edit has run", () => {
    renderCard({
      ...CARD,
      state: "output-available",
      output: {},
      approval: { id: "approval-7", approved: true },
    });
    expect(screen.getByTestId("proposal-decision")).toHaveTextContent("You said yes.");
  });

  it("reads no card off a call of another tool", () => {
    const other: Part = {
      ...CARD,
      type: "tool-consult_user",
      state: "approval-requested",
      approval: { id: "approval-7" },
    };
    expect(findProposal(message(other), CALL_ID)).toBe(null);
  });
});

describe("the researcher's answer reaches the turn", () => {
  it("posts No as a denial carrying the note as its reason", () => {
    const responses: Response[] = [];
    renderCard(PENDING, responses);
    fireEvent.change(screen.getByRole("textbox", { name: "Add a note" }), {
      target: { value: "Not before the orthology check." },
    });
    fireEvent.click(screen.getByRole("button", { name: "No" }));

    expect(responses).toEqual([
      { id: "approval-7", approved: false, reason: "Not before the orthology check." },
    ]);
    expect(useConsultAnswersStore.getState().byApprovalId).toEqual({});
  });

  it("posts Yes with the note as the card's answer on the next request body", () => {
    const responses: Response[] = [];
    renderCard(PENDING, responses);
    fireEvent.change(screen.getByRole("textbox", { name: "Add a note" }), {
      target: { value: "Use the Liverpool strain for Aedes." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Yes" }));

    expect(responses).toEqual([{ id: "approval-7", approved: true }]);
    const body = buildChatRequestBody({
      conversationId: "conv-1",
      siteId: "vectorbase",
      id: "conv-1",
      trigger: "submit-message",
      messages: [message(responded(true))],
      baseBody: undefined,
    });
    expect(body.messages[0]?.parts[1]).toEqual({
      type: "data-user-question-answers",
      data: {
        toolCallId: CALL_ID,
        answers: [
          {
            questionId: "proposal",
            prompt: QUESTION,
            chosenLabels: ["Yes"],
            note: "Use the Liverpool strain for Aedes.",
          },
        ],
      },
    });
  });

  it("posts No with an empty note as a denial with no reason", () => {
    const responses: Response[] = [];
    renderCard(PENDING, responses);
    fireEvent.click(screen.getByRole("button", { name: "No" }));

    expect(responses).toEqual([{ id: "approval-7", approved: false }]);
    expect(useConsultAnswersStore.getState().byApprovalId).toEqual({});
  });

  it("posts Yes with an empty note as an answer whose note is empty", () => {
    const responses: Response[] = [];
    renderCard(PENDING, responses);
    fireEvent.click(screen.getByRole("button", { name: "Yes" }));

    expect(responses).toEqual([{ id: "approval-7", approved: true }]);
    expect(useConsultAnswersStore.getState().answersFor("approval-7")).toEqual([
      { questionId: "proposal", prompt: QUESTION, chosenLabels: ["Yes"], note: "" },
    ]);
  });

  it("sends one approval and opens one turn on a double click of Yes", async () => {
    const sendMessages = openTurn();
    render(<LiveThread sendMessages={sendMessages} />);
    const yes = screen.getByRole("button", { name: "Yes" });

    fireEvent.click(yes);
    fireEvent.click(yes);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });

    expect(sendMessages).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("proposal-decision")).toHaveTextContent("You said yes.");
  });

  it("sends no answers with a declined card", () => {
    const body = buildChatRequestBody({
      conversationId: "conv-1",
      siteId: "vectorbase",
      id: "conv-1",
      trigger: "submit-message",
      messages: [message(responded(false))],
      baseBody: undefined,
    });
    expect(body.messages[0]?.parts).toHaveLength(1);
  });
});
