/**
 * @vitest-environment jsdom
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { UIMessage } from "ai";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "../../../../vitest.msw-setup";
import { ChatHelpersProvider, type ChatHelpers } from "../runtime/chatHelpersContext";
import { TasksPanel } from "./TasksPanel";

const CONVERSATION = "conv-1";
const TASK_ID = "11111111-2222-4333-8444-555555555555";

function makeChat(messages: UIMessage[]): ChatHelpers {
  return {
    id: CONVERSATION,
    messages,
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

function renderPanel(messages: UIMessage[]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <ChatHelpersProvider value={makeChat(messages)}>
        <TasksPanel conversationId={CONVERSATION} />
      </ChatHelpersProvider>
    </QueryClientProvider>,
  );
}

function stubTasks(status: string, error: string | null = null) {
  server.use(
    http.get(`http://localhost:3000/api/v1/conversations/${CONVERSATION}/tasks`, () =>
      HttpResponse.json({
        tasks: [
          {
            taskId: TASK_ID,
            toolName: "run_control_tests_on_step",
            status,
            estimatedDurationSeconds: 120,
            createdAt: "2026-08-30T00:00:00Z",
            error,
          },
        ],
      }),
    ),
  );
}

const RESULT_TURN: UIMessage[] = [
  {
    id: "m1",
    role: "assistant",
    parts: [
      { type: "data-task-completed", data: { taskId: TASK_ID, status: "success" } },
      {
        type: "data-control-test-results",
        data: { taskId: TASK_ID, toolCallId: "call_sLwqd6ToSyX9TDfOm62FTIT6" },
      },
    ] as UIMessage["parts"],
  },
];

describe("the Tasks panel row opens what the task produced", () => {
  it("links a completed row to the exhibit the task produced", async () => {
    stubTasks("complete");
    renderPanel(RESULT_TURN);
    const link = await screen.findByRole("link", { name: /Run control tests/ });
    expect(link.getAttribute("href")).toBe("#table-1");
  });

  it("leaves a row whose task produced no exhibit unlinked", async () => {
    stubTasks("complete");
    renderPanel([
      {
        id: "m1",
        role: "assistant",
        parts: [
          { type: "text", text: "Control tests finished." },
        ] as UIMessage["parts"],
      },
    ]);
    await waitFor(() => {
      expect(screen.getByText("Run control tests")).toBeInTheDocument();
    });
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("leaves a running row unlinked", async () => {
    stubTasks("running");
    renderPanel([]);
    await waitFor(() => {
      expect(screen.getByText("Run control tests")).toBeInTheDocument();
    });
    expect(screen.queryByRole("link")).toBeNull();
  });
});

describe("the Tasks panel reports a task the sweep failed", () => {
  it("marks the row failed and prints the reason the row carries", async () => {
    stubTasks(
      "failed",
      "The worker running this task stopped, which an out-of-memory kill can cause. Ask for it again to retry.",
    );
    renderPanel([]);
    expect(await screen.findByText("Failed")).toBeInTheDocument();
    expect(
      screen.getByText(/The worker running this task stopped/),
    ).toBeInTheDocument();
  });
});

describe("the Tasks panel names every status the runtime writes", () => {
  it("reads Queued for a task no worker has taken, with no percent", async () => {
    stubTasks("pending");
    renderPanel([]);
    expect(await screen.findByText("Queued")).toBeInTheDocument();
    expect(screen.queryByText("pending")).toBeNull();
    expect(screen.queryByText(/%/)).toBeNull();
  });

  it("reads Running for a task a worker runs", async () => {
    stubTasks("running");
    renderPanel([]);
    expect(await screen.findByText("Running")).toBeInTheDocument();
  });

  it("reads Finishing and keeps the spinner while the result waits for its turn", async () => {
    stubTasks("result_ready");
    renderPanel([]);
    const status = await screen.findByText("Finishing");
    const row = status.closest("li");
    expect([
      row?.querySelector(".animate-spin") !== null,
      row?.querySelector(".text-success") === null,
    ]).toEqual([true, true]);
  });

  it("reads Finishing while the result's turn runs", async () => {
    stubTasks("resuming");
    renderPanel([]);
    expect(await screen.findByText("Finishing")).toBeInTheDocument();
  });

  it("reads Complete once the result's turn has run", async () => {
    stubTasks("complete");
    renderPanel([]);
    expect(await screen.findByText("Complete")).toBeInTheDocument();
  });
});
