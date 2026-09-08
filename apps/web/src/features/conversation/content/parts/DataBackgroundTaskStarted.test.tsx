/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { UIMessage } from "ai";
import type { TaskCompleted, TaskProgressChunk } from "@pathfinder/shared";

import {
  ChatHelpersProvider,
  type ChatHelpers,
} from "../../runtime/chatHelpersContext";
import { DataBackgroundTaskStarted } from "./DataBackgroundTaskStarted";

vi.mock("next/navigation", () => ({
  usePathname: () => "/plasmodb/conversation/conv-1",
}));

const STARTED = {
  taskId: "t1",
  toolName: "run_control_tests_on_step",
  estimatedDurationSeconds: 120,
} as const;

function progressPart(data: TaskProgressChunk): UIMessage["parts"][number] {
  return { type: "data-task-progress", data } as UIMessage["parts"][number];
}

function completedPart(data: TaskCompleted): UIMessage["parts"][number] {
  return { type: "data-task-completed", data } as UIMessage["parts"][number];
}

function makeChat(
  parts: UIMessage["parts"][number][],
  resumeStream: () => Promise<void>,
  status: ChatHelpers["status"] = "ready",
  later: UIMessage[] = [],
): ChatHelpers {
  return {
    id: "conv-1",
    messages: [
      {
        id: "m1",
        role: "assistant",
        parts: [
          { type: "data-background-task-started", data: STARTED },
          ...parts,
        ] as UIMessage["parts"],
      },
      ...later,
    ],
    status,
    error: undefined,
    setMessages: () => {},
    sendMessage: async () => {},
    regenerate: async () => {},
    stop: async () => {},
    resumeStream,
    addToolResult: async () => {},
    addToolOutput: async () => {},
    addToolApprovalResponse: () => {},
    clearError: () => {},
  };
}

function renderCard(
  parts: UIMessage["parts"][number][],
  options: {
    resumeStream?: () => Promise<void>;
    status?: ChatHelpers["status"];
    later?: UIMessage[];
  } = {},
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const chat = makeChat(
    parts,
    options.resumeStream ?? (async () => {}),
    options.status ?? "ready",
    options.later ?? [],
  );
  const ui = (
    <QueryClientProvider client={client}>
      <ChatHelpersProvider value={chat}>
        <DataBackgroundTaskStarted data={STARTED} />
      </ChatHelpersProvider>
    </QueryClientProvider>
  );
  return { ...render(ui), ui };
}

describe("DataBackgroundTaskStarted", () => {
  it("draws one task row named by the tool, with the estimate the wire gave", () => {
    renderCard([]);
    const card = screen.getByTestId("data-background-task-started");
    expect(card).toHaveTextContent("Run control tests");
    expect(screen.getByTestId("task-row-elapsed")).toHaveTextContent("~120 s");
  });

  it("drives the progress bar from the message's own progress part", () => {
    renderCard([
      progressPart({ taskId: "t1", percent: 0.6, message: "Comparing controls" }),
    ]);
    expect(screen.getByText("Comparing controls")).toBeInTheDocument();
    expect(screen.getByTestId("task-row-status")).toHaveTextContent("60%");
    expect(screen.getByTestId("progress-bar-fill")).toHaveStyle({ width: "60%" });
  });

  it("reads Completed and keeps its bar once the job succeeds", () => {
    renderCard([
      progressPart({ taskId: "t1", percent: 0.6, message: "Comparing controls" }),
      completedPart({ taskId: "t1", status: "success" }),
    ]);
    const completed = screen.getByTestId("data-task-completed");
    expect(screen.getByTestId("task-row-status")).toHaveTextContent("Completed");
    expect(within(completed).getByTestId("progress-bar-fill")).toHaveStyle({
      width: "100%",
    });
    expect(screen.queryByText("Comparing controls")).toBeNull();
  });

  it("renders a failed completion with the worker's error text", () => {
    renderCard([
      completedPart({
        taskId: "t1",
        status: "failed",
        error: "WDK rejected the search",
      }),
    ]);
    const completed = screen.getByTestId("data-task-completed");
    expect(screen.getByTestId("task-row-status")).toHaveTextContent("Failed");
    expect(completed).toHaveTextContent("WDK rejected the search");
  });

  it("puts no call JSON on the page in any state", () => {
    const { container } = renderCard([
      progressPart({ taskId: "t1", percent: 0.6, message: "Comparing controls" }),
      completedPart({ taskId: "t1", status: "success" }),
    ]);
    expect(container.textContent).not.toContain("{");
    expect(container.textContent).toContain("Run control tests");
  });

  it("ignores parts that belong to another task", () => {
    renderCard([
      progressPart({ taskId: "other", percent: 0.9, message: "Not this task" }),
      completedPart({ taskId: "other", status: "success" }),
    ]);
    expect(screen.queryAllByText("Not this task")).toHaveLength(0);
    expect(screen.queryAllByTestId("data-task-completed")).toHaveLength(0);
    expect(screen.getByTestId("task-row-status")).toHaveTextContent("0%");
  });

  it("draws one row per lane, ordered by lane, when the task fans out", () => {
    renderCard([
      progressPart({
        taskId: "t1",
        percent: 0.5,
        message: "Trying v2",
        toolSpecific: { variantId: "v2" },
      }),
      progressPart({
        taskId: "t1",
        percent: 0.2,
        message: "Trying v1",
        toolSpecific: { variantId: "v1" },
      }),
      progressPart({
        taskId: "t1",
        percent: 0.9,
        message: "Trying v2 again",
        toolSpecific: { variantId: "v2" },
      }),
    ]);

    const rows = screen.getAllByTestId("task-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("v1");
    expect(rows[0]).toHaveTextContent("20%");
    expect(rows[1]).toHaveTextContent("v2");
    expect(rows[1]).toHaveTextContent("90%");
  });

  it("spaces its lanes with the one paragraph gap the rows no longer carry", () => {
    renderCard([
      progressPart({
        taskId: "t1",
        percent: 0.5,
        message: "Trying v2",
        toolSpecific: { variantId: "v2" },
      }),
      progressPart({
        taskId: "t1",
        percent: 0.2,
        message: "Trying v1",
        toolSpecific: { variantId: "v1" },
      }),
    ]);

    const card = screen.getByTestId("data-background-task-started");
    expect(card.className.split(/\s+/)).toContain("gap-3");
    expect(screen.getAllByTestId("task-row")[0]?.className).toBe("");
  });

  it("keeps a single row for a task that runs one sequence", () => {
    renderCard([
      progressPart({ taskId: "t1", percent: 0.4, message: "Comparing controls" }),
    ]);

    expect(screen.getAllByTestId("task-row")).toHaveLength(1);
  });

  it("marks every lane completed once the task finishes", () => {
    renderCard([
      progressPart({
        taskId: "t1",
        percent: 0.5,
        message: "Trying v1",
        toolSpecific: { variantId: "v1" },
      }),
      progressPart({
        taskId: "t1",
        percent: 0.6,
        message: "Trying v2",
        toolSpecific: { variantId: "v2" },
      }),
      completedPart({ taskId: "t1", status: "success" }),
    ]);

    const statuses = screen
      .getAllByTestId("task-row-status")
      .map((node) => node.textContent);
    expect(statuses).toEqual(["Completed", "Completed"]);
  });

  it("reattaches the thread exactly once while the task is unfinished", async () => {
    const resumeStream = vi.fn(async () => {});
    const { rerender, ui } = renderCard([], { resumeStream });
    await waitFor(() => {
      expect(resumeStream).toHaveBeenCalledTimes(1);
    });
    rerender(ui);
    await waitFor(() => {
      expect(resumeStream).toHaveBeenCalledTimes(1);
    });
  });

  it("does not reattach while the suspending turn is still streaming", async () => {
    const resumeStream = vi.fn(async () => {});
    renderCard([], { resumeStream, status: "streaming" });
    await Promise.resolve();
    expect(resumeStream).not.toHaveBeenCalled();
  });

  it("renders a reloaded finished card without reattaching the thread", async () => {
    const resumeStream = vi.fn(async () => {});
    renderCard(
      [
        progressPart({ taskId: "t1", percent: 1, message: "Scoring" }),
        completedPart({ taskId: "t1", status: "success" }),
      ],
      { resumeStream },
    );
    expect(screen.getByTestId("task-row-status")).toHaveTextContent("Completed");
    await Promise.resolve();
    expect(resumeStream).not.toHaveBeenCalled();
  });
});

const EXHIBIT = {
  taskId: "t1",
  toolCallId: "call_1",
  targetLabel: "Genes by Molecular Weight",
  targetEstimatedSize: 132,
  positive: { controlsCount: 3, intersectionCount: 2, recall: 2 / 3 },
};

function exhibitPart(): UIMessage["parts"][number] {
  return {
    type: "data-control-test-results",
    data: EXHIBIT,
  } as UIMessage["parts"][number];
}

function summaryPart(summary: string): UIMessage["parts"][number] {
  return {
    type: "data-tool-summary",
    data: { toolCallId: "call_1", summary, status: "ok" },
  } as UIMessage["parts"][number];
}

describe("a completed task points at its exhibit", () => {
  it("links to no exhibit, because the exhibit reads under the row", () => {
    renderCard([completedPart({ taskId: "t1", status: "success" }), exhibitPart()]);
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });

  it("reads the tool's own line in place of Completed", () => {
    renderCard([
      completedPart({ taskId: "t1", status: "success" }),
      exhibitPart(),
      summaryPart("2 of 3 positive controls recovered"),
    ]);
    expect(screen.getByTestId("task-row-status")).toHaveTextContent(
      "2 of 3 positive controls recovered",
    );
  });

  it("offers no link while the task still runs", () => {
    renderCard([]);
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });

  it("offers no link for a task whose turn wrote only prose", () => {
    renderCard([completedPart({ taskId: "t1", status: "success" })], {
      later: [
        {
          id: "m2",
          role: "assistant",
          parts: [{ type: "text", text: "Enrichment finished." }] as UIMessage["parts"],
        },
      ],
    });
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });

  it("offers no link for a task that failed", () => {
    renderCard([
      completedPart({ taskId: "t1", status: "failed", error: "boom" }),
      exhibitPart(),
    ]);
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });
});
