import type { UIMessage } from "ai";
import { describe, expect, it } from "vitest";

import { taskResult } from "./taskExhibit";

const TASK = "3d221443-0074-47d8-8300-addadd147989";
const CALL = "call_sLwqd6ToSyX9TDfOm62FTIT6";

function assistant(id: string, parts: UIMessage["parts"]): UIMessage {
  return { id, role: "assistant", parts };
}

function exhibit(taskId: string, toolCallId: string): UIMessage["parts"][number] {
  return {
    type: "data-control-test-results",
    data: {
      taskId,
      toolCallId,
      targetLabel: "Genes by Molecular Weight",
      targetEstimatedSize: 132,
      positive: { controlsCount: 3, intersectionCount: 2, recall: 2 / 3 },
    },
  };
}

function toolSummary(toolCallId: string, summary: string): UIMessage["parts"][number] {
  return {
    type: "data-tool-summary",
    data: { toolCallId, summary, status: "ok" },
  };
}

function subAgentStep(
  toolCallId: string,
  resultSummary: string,
): UIMessage["parts"][number] {
  return {
    type: "data-sub-agent-step",
    data: {
      parentToolCallId: "call_parent",
      kind: "tool",
      state: "completed",
      toolCallId,
      toolName: "run_control_tests_on_step",
      resultSummary,
    },
  };
}

describe("what a finished task's row reads off the thread", () => {
  it("cross-references the exhibit the task produced", () => {
    const messages = [assistant("m1", [exhibit(TASK, CALL)])];
    expect(taskResult(messages, TASK).reference).toEqual({
      label: "see Table 1",
      href: "#table-1",
    });
  });

  it("numbers the exhibit by its place among the thread's tables", () => {
    const messages = [
      assistant("m1", [
        { type: "data-scored-comparison", data: { objective: "mcc", variants: [] } },
        exhibit(TASK, CALL),
      ] as UIMessage["parts"]),
    ];
    expect(taskResult(messages, TASK).reference?.href).toBe("#table-2");
  });

  it("reads the line the Lead's own call wrote", () => {
    const messages = [
      assistant("m1", [
        exhibit(TASK, CALL),
        toolSummary(CALL, "2 of 3 positive controls recovered"),
      ]),
    ];
    expect(taskResult(messages, TASK).summary).toBe(
      "2 of 3 positive controls recovered",
    );
  });

  it("reads the line a sub-agent's call wrote on its step row", () => {
    const messages = [
      assistant("m1", [
        exhibit(TASK, CALL),
        subAgentStep(CALL, "2 of 3 positive controls recovered"),
      ]),
    ];
    expect(taskResult(messages, TASK).summary).toBe(
      "2 of 3 positive controls recovered",
    );
  });

  it("ignores a line another call wrote", () => {
    const messages = [
      assistant("m1", [exhibit(TASK, CALL), toolSummary("call_other", "16 steps")]),
    ];
    expect(taskResult(messages, TASK).summary).toBe(null);
  });

  it("cross-references nothing for a task that produced no exhibit", () => {
    const messages = [assistant("m1", [exhibit("another-task", CALL)])];
    expect(taskResult(messages, TASK)).toEqual({ summary: null, reference: null });
  });
});
