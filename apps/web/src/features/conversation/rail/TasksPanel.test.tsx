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
            toolName: "run_gene_set_enrichment",
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
      { type: "data-enrichment-results", data: { taskId: TASK_ID } },
    ] as UIMessage["parts"],
  },
];

describe("the Tasks panel row opens what the task produced", () => {
  it("links a completed row to the exhibit the task produced", async () => {
    stubTasks("complete");
    renderPanel(RESULT_TURN);
    const link = await screen.findByRole("link", { name: /Gene-set enrichment/ });
    expect(link.getAttribute("href")).toBe("#table-1");
  });

  it("leaves a row whose task produced no exhibit unlinked", async () => {
    stubTasks("complete");
    renderPanel([
      {
        id: "m1",
        role: "assistant",
        parts: [{ type: "text", text: "Enrichment finished." }] as UIMessage["parts"],
      },
    ]);
    await waitFor(() => {
      expect(screen.getByText("Gene-set enrichment")).toBeInTheDocument();
    });
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("leaves a running row unlinked", async () => {
    stubTasks("running");
    renderPanel([]);
    await waitFor(() => {
      expect(screen.getByText("Gene-set enrichment")).toBeInTheDocument();
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
    expect(await screen.findByText("failed")).toBeInTheDocument();
    expect(
      screen.getByText(/The worker running this task stopped/),
    ).toBeInTheDocument();
  });
});
