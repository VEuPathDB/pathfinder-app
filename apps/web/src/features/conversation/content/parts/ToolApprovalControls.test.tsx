/**
 * @vitest-environment jsdom
 */
import type { UIMessage } from "ai";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { toast } from "sonner";

import { useSettingsStore } from "@/state/useSettingsStore";

import {
  ChatHelpersProvider,
  type ChatHelpers,
} from "../../runtime/chatHelpersContext";
import { ToolApprovalControls, findToolApproval } from "./ToolApprovalControls";

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

beforeEach(() => {
  vi.mocked(toast.error).mockClear();
  useSettingsStore.setState({ showRawToolCalls: false, showTokenUsage: true });
});

function assistantMessage(parts: UIMessage["parts"]): UIMessage {
  return { id: "m1", role: "assistant", parts };
}

function pendingPart(toolType: `tool-${string}`): UIMessage["parts"][number] {
  return {
    type: toolType,
    toolCallId: "call-1",
    state: "approval-requested",
    input: { stepId: "step-7" },
    approval: { id: "appr-1" },
  };
}

function makeChat(
  messages: UIMessage[],
  addToolApprovalResponse: ChatHelpers["addToolApprovalResponse"],
): ChatHelpers {
  return {
    id: "conv-1",
    messages,
    status: "ready",
    error: undefined,
    setMessages: () => {},
    sendMessage: async () => {},
    regenerate: async () => {},
    stop: async () => {},
    addToolResult: async () => {},
    addToolOutput: async () => {},
    addToolApprovalResponse,
    clearError: () => {},
  };
}

function renderControls(
  parts: UIMessage["parts"],
  respond: ChatHelpers["addToolApprovalResponse"] = () => {},
) {
  const chat = makeChat([assistantMessage(parts)], respond);
  return render(
    <ChatHelpersProvider value={chat}>
      <ToolApprovalControls toolCallId="call-1" />
    </ChatHelpersProvider>,
  );
}

describe("findToolApproval", () => {
  it("reads the approval id, tool name and input off a pending approval part", () => {
    const view = findToolApproval(
      [assistantMessage([pendingPart("tool-delete_step")])],
      "call-1",
    );
    expect(view).not.toBeNull();
    expect(view?.approvalId).toBe("appr-1");
    expect(view?.toolName).toBe("delete_step");
    expect(view?.decision).toBe("pending");
    expect(view?.input).toEqual({ stepId: "step-7" });
  });

  it("reports approved once the SDK marks the part approval-responded", () => {
    const view = findToolApproval(
      [
        assistantMessage([
          {
            type: "tool-clear_strategy",
            toolCallId: "call-1",
            state: "approval-responded",
            input: {},
            approval: { id: "appr-1", approved: true },
          },
        ]),
      ],
      "call-1",
    );
    expect(view?.decision).toBe("approved");
  });

  it("reports denied for a denied response and for a denied output", () => {
    const responded = findToolApproval(
      [
        assistantMessage([
          {
            type: "tool-clear_strategy",
            toolCallId: "call-1",
            state: "approval-responded",
            input: {},
            approval: { id: "appr-1", approved: false },
          },
        ]),
      ],
      "call-1",
    );
    expect(responded?.decision).toBe("denied");

    const output = findToolApproval(
      [
        assistantMessage([
          {
            type: "tool-clear_strategy",
            toolCallId: "call-1",
            state: "output-denied",
            input: {},
            approval: { id: "appr-1", approved: false },
          },
        ]),
      ],
      "call-1",
    );
    expect(output?.decision).toBe("denied");
  });

  it("ignores tool parts that carry no approval and unmatched call ids", () => {
    const parts: UIMessage["parts"] = [
      {
        type: "tool-get_strategy",
        toolCallId: "call-1",
        state: "input-available",
        input: {},
      },
    ];
    expect(findToolApproval([assistantMessage(parts)], "call-1")).toBe(null);
    expect(
      findToolApproval([assistantMessage([pendingPart("tool-delete_step")])], "call-2"),
    ).toBe(null);
  });
});

const ASKED = "Delete step 'Transform by Orthology' (GenesByOrthologs, 142 genes)?";

function summaryPart(summary: string): UIMessage["parts"][number] {
  return {
    type: "data-tool-summary",
    data: { toolCallId: "call-1", summary, status: "ok" },
  };
}

describe("ToolApprovalControls", () => {
  it("names the step a delete removes by the line written when it asked", () => {
    renderControls([pendingPart("tool-delete_step"), summaryPart(ASKED)]);
    expect(screen.getByTestId("approval-card-title")).toHaveTextContent(ASKED);
  });

  it("keeps the asked line on a replayed card after the step is gone", () => {
    renderControls([
      {
        type: "tool-delete_step",
        toolCallId: "call-1",
        state: "output-available",
        input: { stepId: "c_orthologs_pvivax_p01" },
        output: { ok: true },
        approval: { id: "appr-1", approved: true },
      },
      summaryPart(ASKED),
      summaryPart("Deleted c_orthologs_pvivax_p01, 3 steps left"),
    ]);
    expect(screen.getByTestId("tool-approval-decision")).toHaveTextContent(
      `Approved: ${ASKED}`,
    );
  });

  it("keeps the bespoke question of a tool the api does not name", () => {
    renderControls([
      pendingPart("tool-clear_strategy"),
      summaryPart("Cleared 3 steps"),
    ]);
    expect(screen.getByTestId("approval-card-title")).toHaveTextContent(
      "Clear the strategy? This removes every step from this conversation and from VEuPathDB.",
    );
  });

  it("asks the question in one card that names the tool", () => {
    renderControls([pendingPart("tool-delete_step")]);
    expect(screen.getByTestId("approval-card-title")).toHaveTextContent(
      "Delete step needs your approval before it runs.",
    );
    expect(screen.getByTestId("tool-approval-approve")).toBeInTheDocument();
    expect(screen.getByTestId("tool-approval-deny")).toBeInTheDocument();
  });

  it("names what a deletion removes instead of the standing sentence", () => {
    renderControls([pendingPart("tool-clear_strategy")]);
    expect(screen.getByTestId("approval-card-title")).toHaveTextContent(
      "Clear the strategy? This removes every step from this conversation and from VEuPathDB.",
    );
    expect(screen.getByTestId("approval-card-title")).not.toHaveTextContent(
      "needs your approval before it runs",
    );
  });

  it("keeps the call's input out of the card while the dev flag is off", () => {
    useSettingsStore.setState({ showRawToolCalls: false });
    const { container } = renderControls([pendingPart("tool-delete_step")]);
    expect(screen.getByTestId("approval-card")).toBeInTheDocument();
    expect(container.textContent).not.toContain("step-7");
    expect(container.textContent).not.toContain("stepId");
  });

  it("shows the call's input in the card while the dev flag is on", () => {
    useSettingsStore.setState({ showRawToolCalls: true });
    const { container } = renderControls([pendingPart("tool-delete_step")]);
    expect(container.textContent).toContain("stepId");
    expect(container.textContent).toContain("step-7");
  });

  it("approves with the approval id from the part", () => {
    const respond = vi.fn();
    renderControls([pendingPart("tool-optimize_search_parameters")], respond);
    fireEvent.click(screen.getByTestId("tool-approval-approve"));
    expect(respond).toHaveBeenCalledWith({ id: "appr-1", approved: true });
  });

  it("denies with the approval id from the part", () => {
    const respond = vi.fn();
    renderControls([pendingPart("tool-clear_strategy")], respond);
    fireEvent.click(screen.getByTestId("tool-approval-deny"));
    expect(respond).toHaveBeenCalledWith({ id: "appr-1", approved: false });
  });

  it("reports a rejected approval response through toast.error", async () => {
    const respond = vi.fn(() => Promise.reject(new Error("network down")));
    renderControls([pendingPart("tool-delete_step")], respond);
    fireEvent.click(screen.getByTestId("tool-approval-approve"));
    await waitFor(() => {
      expect(vi.mocked(toast.error)).toHaveBeenCalledWith("Approval could not be sent");
    });
  });

  it("renders nothing for consult_user, which the consult carousel owns", () => {
    renderControls([pendingPart("tool-consult_user")]);
    expect(screen.queryByTestId("tool-approval-controls")).not.toBeInTheDocument();
    expect(screen.queryByTestId("tool-approval-decision")).not.toBeInTheDocument();
  });

  it("renders nothing for propose_changes, which the proposal card owns", () => {
    renderControls([pendingPart("tool-propose_changes")]);
    expect(screen.queryByTestId("tool-approval-controls")).not.toBeInTheDocument();
    expect(screen.queryByTestId("tool-approval-decision")).not.toBeInTheDocument();
  });

  it("renders nothing for adopt_separating_strategy, which the separation card owns", () => {
    renderControls([pendingPart("tool-adopt_separating_strategy")]);
    expect(screen.queryByTestId("tool-approval-controls")).not.toBeInTheDocument();
    expect(screen.queryByTestId("tool-approval-decision")).not.toBeInTheDocument();
  });

  it("replaces the buttons with the recorded decision once answered", () => {
    renderControls([
      {
        type: "tool-delete_step",
        toolCallId: "call-1",
        state: "approval-responded",
        input: {},
        approval: { id: "appr-1", approved: false },
      },
    ]);
    expect(screen.queryByTestId("tool-approval-approve")).not.toBeInTheDocument();
    expect(screen.getByTestId("tool-approval-decision")).toHaveTextContent("Denied");
  });

  it("renders nothing when the tool call carries no approval", () => {
    renderControls([
      {
        type: "tool-get_strategy",
        toolCallId: "call-1",
        state: "input-available",
        input: {},
      },
    ]);
    expect(screen.queryByTestId("tool-approval-controls")).not.toBeInTheDocument();
  });
});
