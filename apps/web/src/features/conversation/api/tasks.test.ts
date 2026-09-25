import { describe, expect, it } from "vitest";

import type { TaskListItemStatusEnumKey } from "@pathfinder/shared/generated/types/TaskListItem";

import { TASK_STATUSES, taskPollInterval } from "./tasks";

function listOf(status: TaskListItemStatusEnumKey) {
  return {
    tasks: [
      {
        taskId: "11111111-2222-4333-8444-555555555555",
        toolName: "run_control_tests_on_step",
        status,
        estimatedDurationSeconds: 120,
        createdAt: "2026-08-30T00:00:00Z",
      },
    ],
  };
}

describe("taskPollInterval", () => {
  it("polls while any task is queued, running or finishing, and stops after", () => {
    const polls = Object.fromEntries(
      TASK_STATUSES.map((status) => [status, taskPollInterval(listOf(status))]),
    );
    expect(polls).toEqual({
      pending: 3_000,
      running: 3_000,
      result_ready: 3_000,
      resuming: 3_000,
      complete: false,
      failed: false,
    });
  });

  it("does not poll before the first read answers", () => {
    expect(taskPollInterval(undefined)).toBe(false);
  });
});
