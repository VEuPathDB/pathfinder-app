/**
 * @vitest-environment jsdom
 */
import type { UIMessage } from "ai";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { SeparationReport } from "@pathfinder/shared";

import recorded from "../../__fixtures__/separationResult.json";
import {
  ChatHelpersProvider,
  type ChatHelpers,
} from "../../runtime/chatHelpersContext";
import { findAdoption } from "./separationCardData";
import { chatHelpersFor, threadPart, type ThreadPart } from "./threadFixture";

vi.mock("@assistant-ui/react", () => ({
  useAuiState: (select: (s: { message: { id: string } }) => unknown) =>
    select({ message: { id: "m1" } }),
}));

import { SeparationCard } from "./SeparationCard";

const REPORT = recorded as SeparationReport;
const CALL_ID = "call_adopt_separating_strategy";

const CARD = {
  type: "tool-adopt_separating_strategy",
  toolCallId: CALL_ID,
  input: { task_id: REPORT.taskId },
} as const;

const PENDING: ThreadPart = {
  ...CARD,
  state: "approval-requested",
  approval: { id: "approval-9" },
};

type Response = Parameters<ChatHelpers["addToolApprovalResponse"]>[0];

function messages(card: ThreadPart): UIMessage[] {
  return [
    {
      id: "m1",
      role: "assistant",
      parts: [threadPart("data-separation-result", REPORT), card],
    },
  ];
}

function renderCard(card: ThreadPart, responses: Response[] = []): void {
  render(
    <ChatHelpersProvider
      value={{
        ...chatHelpersFor(messages(card)),
        addToolApprovalResponse: (response) => {
          responses.push(response);
        },
      }}
    >
      <SeparationCard toolCallId={CALL_ID} />
    </ChatHelpersProvider>,
  );
}

afterEach(() => cleanup());

describe("the separation card", () => {
  it("asks the question the run's counts wrote", () => {
    renderCard(PENDING);

    expect(screen.getByTestId("separation-question").textContent).toBe(
      "Build the closest strategy found: 3 searches returning 61 of 80 " +
        "positives and 2 of 40 negatives in 1,132 genes?",
    );
    expect(screen.getByRole("button", { name: "Yes" })).toBeEnabled();
  });

  it("sends the approval for its own call on a yes", () => {
    const responses: Response[] = [];
    renderCard(PENDING, responses);

    fireEvent.click(screen.getByRole("button", { name: "Yes" }));

    expect(responses).toEqual([{ id: "approval-9", approved: true }]);
  });

  it("sends a no with the note as its reason", () => {
    const responses: Response[] = [];
    renderCard(PENDING, responses);
    fireEvent.change(screen.getByRole("textbox", { name: "Why not" }), {
      target: { value: "Keep the strategy I have." },
    });

    fireEvent.click(screen.getByRole("button", { name: "No" }));

    expect(responses).toEqual([
      { id: "approval-9", approved: false, reason: "Keep the strategy I have." },
    ]);
  });

  it("shows the answer once the card is declined", () => {
    renderCard({
      ...CARD,
      state: "output-denied",
      approval: { id: "approval-9", approved: false },
    });

    expect(screen.getByTestId("separation-decision").textContent).toBe("You said no.");
    expect(screen.queryByRole("button", { name: "Yes" })).toBeNull();
  });

  it("reads no card when no result carries the task", () => {
    const other: ThreadPart = { ...PENDING, input: { task_id: "another-task" } };

    expect(findAdoption(messages(other), "m1", CALL_ID)).toBe(null);
  });
});
