/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import type { UIMessage } from "ai";
import { reduceSnapshot, type MessagePart } from "@pathfinder/assistant-client";
import type { DataSubAgentCallPayload } from "@pathfinder/shared";

import { useSettingsStore } from "@/state/useSettingsStore";

import { ChatHelpersProvider, type ChatHelpers } from "../runtime/chatHelpersContext";
import { SubAgentTraceAnchor, TraceAnchor } from "./TraceAnchor";
import recordedTurn from "../__fixtures__/recordedTurn.json";

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn(), message: vi.fn() },
  Toaster: () => null,
}));

const ROW_LABELS = [
  "Find studies",
  "Open study",
  "Find searches",
  "Choose a search",
  "Preview samples",
  "Run control tests",
  "Optimize parameters",
];

function turnParts(): MessagePart[] {
  const assistant = reduceSnapshot(recordedTurn as unknown[]).find(
    (message) => message.role === "assistant",
  );
  if (assistant === undefined) throw new Error("the recorded turn holds no message");
  return assistant.parts;
}

function chatWith(
  parts: MessagePart[],
  status: ChatHelpers["status"] = "ready",
): ChatHelpers {
  const message: UIMessage = { id: "m1", role: "assistant", parts };
  return {
    id: "conv-1",
    messages: [message],
    status,
    error: undefined,
    setMessages: () => {},
    sendMessage: async () => {},
    regenerate: async () => {},
    stop: async () => {},
    resumeStream: async () => {},
    addToolResult: async () => {},
    addToolOutput: async () => {},
    addToolApprovalResponse: () => {},
    clearError: () => {},
  };
}

const DISPATCH: DataSubAgentCallPayload = {
  toolCallId: "sa_9",
  subAgent: "build_strategy",
  phase: "execution",
  state: "started",
};

function openDispatch(): MessagePart[] {
  return [
    { type: "data-sub-agent-call", id: "sa_9", data: DISPATCH },
    {
      type: "data-sub-agent-step",
      data: {
        parentToolCallId: "sa_9",
        kind: "tool",
        state: "started",
        toolCallId: "s1",
        toolName: "set_criterion",
        args: { criterionId: "c1" },
      },
    },
  ];
}

const LEAD_USAGE: MessagePart = {
  type: "data-lead-usage",
  id: "lu_1",
  data: { modelId: "openai:gpt-5.6-luna", tokens: 41800, costUsd: "0.0131" },
};

/** Two stretches of work with the Lead's prose between them. */
function twoRuns(): MessagePart[] {
  return [
    {
      type: "tool-search_eda_studies",
      toolCallId: "call_a",
      state: "output-available",
      input: {},
      output: {},
    },
    { type: "text", text: "Here is what I found." },
    {
      type: "tool-set_criterion",
      toolCallId: "call_b",
      state: "output-available",
      input: {},
      output: {},
    },
    LEAD_USAGE,
  ] as MessagePart[];
}

function stoppedDispatch(): MessagePart[] {
  return [...openDispatch(), { type: "data-turn-stopped", data: {} }];
}

function anchorFor(toolCallId: string, toolName: string, parts = turnParts()) {
  useSettingsStore.setState({ showRawToolCalls: false, showTokenUsage: true });
  return render(
    <ChatHelpersProvider value={chatWith(parts)}>
      <TraceAnchor
        toolName={toolName}
        toolCallId={toolCallId}
        args={{}}
        result={undefined}
        status={{ type: "complete" }}
      />
    </ChatHelpersProvider>,
  );
}

describe("TraceAnchor", () => {
  it("draws the whole run once, at the run's first row-bearing part", () => {
    const view = anchorFor("call_1", "search_eda_studies");
    expect(view.getAllByTestId("turn-trace")).toHaveLength(1);
    const rows = view.getAllByTestId("trace-row");
    expect(rows).toHaveLength(7);
    expect(rows.map((node) => node.textContent)).toEqual(
      expect.arrayContaining([expect.stringContaining("Find studies")]),
    );
    ROW_LABELS.forEach((label, index) => {
      expect(rows[index]).toHaveTextContent(label);
    });
  });

  it("draws nothing at any later tool call of the same run", () => {
    for (const id of ["call_2", "call_3", "call_4", "call_5"]) {
      const view = anchorFor(id, "open_eda_analysis");
      expect(view.container.innerHTML).toBe("");
      view.unmount();
    }
  });

  it("draws nothing at a sub-agent call that did not open the run", () => {
    const view = render(
      <ChatHelpersProvider value={chatWith(turnParts())}>
        <SubAgentTraceAnchor
          data={{
            toolCallId: "sa_1",
            subAgent: "frame_problem",
            phase: "frame",
            state: "completed",
          }}
        />
      </ChatHelpersProvider>,
    );
    expect(view.container.innerHTML).toBe("");
  });

  it("labels the run's three groups through the shared phase labels", () => {
    const view = anchorFor("call_1", "search_eda_studies");
    expect(view.getAllByTestId("trace-group-label").map((n) => n.textContent)).toEqual([
      "Assistant",
      "Planning",
      "Assistant",
    ]);
  });

  it("carries the approval the run is waiting on", () => {
    const view = anchorFor("call_1", "search_eda_studies");
    expect(view.getAllByTestId("approval-card")).toHaveLength(1);
    expect(view.getByTestId("approval-card-title")).toHaveTextContent(
      "Optimize parameters needs your approval before it runs.",
    );
  });

  it("prints the turn's model with the whole turn's tokens and cost", () => {
    const view = anchorFor("call_1", "search_eda_studies");
    expect(view.getByTestId("trace-usage")).toHaveTextContent(
      "gpt-5.6-luna - 54.1K, $0.02",
    );
  });

  it("prints the turn's usage once, on the last run of the message", () => {
    const first = anchorFor("call_a", "search_eda_studies", twoRuns());
    expect(first.queryAllByTestId("trace-usage")).toHaveLength(0);
    expect(first.getAllByTestId("trace-row")).toHaveLength(1);
    first.unmount();

    const last = anchorFor("call_b", "set_criterion", twoRuns());
    expect(last.getByTestId("trace-usage")).toHaveTextContent(
      "gpt-5.6-luna - 41.8K, $0.01",
    );
  });

  it("prints no usage line when the dev flag is off", () => {
    useSettingsStore.setState({ showRawToolCalls: false, showTokenUsage: false });
    const view = render(
      <ChatHelpersProvider value={chatWith(turnParts())}>
        <TraceAnchor
          toolName="search_eda_studies"
          toolCallId="call_1"
          args={{}}
          result={undefined}
          status={{ type: "complete" }}
        />
      </ChatHelpersProvider>,
    );
    expect(view.queryAllByTestId("trace-usage")).toHaveLength(0);
    expect(view.getAllByTestId("trace-row")).toHaveLength(7);
  });

  it("prints no usage line for a message that carries no lead usage", () => {
    useSettingsStore.setState({ showRawToolCalls: false, showTokenUsage: true });
    const view = render(
      <ChatHelpersProvider value={chatWith(openDispatch())}>
        <SubAgentTraceAnchor data={DISPATCH} />
      </ChatHelpersProvider>,
    );
    expect(view.queryAllByTestId("trace-usage")).toHaveLength(0);
    expect(view.getAllByTestId("trace-row")).toHaveLength(1);
  });

  it("names no figure, no notice and no task among its rows", () => {
    const view = anchorFor("call_1", "search_eda_studies");
    const text = view.getAllByTestId("trace-row").map((node) => node.textContent);
    expect(text.join(" ")).not.toContain("eda.viz");
    expect(text.join(" ")).not.toContain("turn-failed");
    expect(view.queryAllByTestId("figure")).toHaveLength(0);
    expect(view.queryAllByTestId("task-row")).toHaveLength(0);
  });

  it("puts no call JSON in the thread while the dev flag is off", () => {
    const view = anchorFor("call_1", "search_eda_studies");
    expect(view.container.textContent).not.toContain("wdkStepId");
    expect(view.container.textContent).not.toContain("datasetId");
  });

  it("draws no group for a dispatch payload the wire's schema refuses", () => {
    const view = render(
      <ChatHelpersProvider value={chatWith(openDispatch())}>
        <SubAgentTraceAnchor
          data={
            { subAgent: "frame_problem", phase: "frame", state: "started" } as never
          }
        />
      </ChatHelpersProvider>,
    );
    expect(view.container.innerHTML).toBe("");
  });

  it("reads a dispatch the user's stop left open as Stopped", () => {
    useSettingsStore.setState({ showRawToolCalls: false, showTokenUsage: true });
    const view = render(
      <ChatHelpersProvider value={chatWith(stoppedDispatch())}>
        <SubAgentTraceAnchor data={DISPATCH} />
      </ChatHelpersProvider>,
    );
    expect(view.getByTestId("trace-group-state")).toHaveTextContent("Stopped");
    expect(view.getByTestId("trace-row-summary")).toHaveTextContent("Stopped");
    expect(view.getByTestId("trace-row-status")).not.toHaveClass("animate-spin");
    expect(view.getByTestId("turn-trace-summary")).toHaveTextContent("1 step");
    expect(view.getByTestId("turn-trace-toggle")).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("reads a dispatch of a turn that ended saying nothing as Not finished", () => {
    useSettingsStore.setState({ showRawToolCalls: false, showTokenUsage: true });
    const view = render(
      <ChatHelpersProvider value={chatWith(openDispatch())}>
        <SubAgentTraceAnchor data={DISPATCH} />
      </ChatHelpersProvider>,
    );
    expect(view.getByTestId("trace-group-state")).toHaveTextContent("Not finished");
    expect(view.getByTestId("trace-row-status")).toHaveClass("animate-spin");
    expect(view.getByTestId("turn-trace-summary")).toHaveTextContent("Working...");
  });

  it("says nothing about a dispatch of the turn still streaming", () => {
    useSettingsStore.setState({ showRawToolCalls: false, showTokenUsage: true });
    const view = render(
      <ChatHelpersProvider value={chatWith(openDispatch(), "streaming")}>
        <SubAgentTraceAnchor data={DISPATCH} />
      </ChatHelpersProvider>,
    );
    expect(view.queryByTestId("trace-group-state")).toBeNull();
    expect(view.getByTestId("turn-trace-summary")).toHaveTextContent("Working...");
  });

  it("draws no row for a summary the wire's schema refuses", () => {
    // A summary the wire's schema refuses: the field is not a string.
    const malformed = {
      type: "tool-set_criterion",
      toolCallId: "call_x",
      state: "output-available",
      input: {},
      output: { ok: true },
      summary: 42,
    } as unknown as MessagePart;
    const parts: MessagePart[] = [malformed];
    const view = render(
      <ChatHelpersProvider value={chatWith(parts)}>
        <TraceAnchor
          toolName="set_criterion"
          toolCallId="call_x"
          args={{}}
          result={undefined}
          status={{ type: "complete" }}
        />
      </ChatHelpersProvider>,
    );
    expect(view.getAllByTestId("trace-row")).toHaveLength(1);
    expect(view.queryAllByTestId("trace-row-summary")).toHaveLength(0);
  });
});
