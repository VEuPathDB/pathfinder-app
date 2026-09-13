"use client";

import {
  orderedLanes,
  taskLifecycle,
  type TaskCompletion,
  type TaskProgress,
} from "@veupathdb/assistant-client";
import { z } from "zod";
import type { BackgroundTaskStarted } from "@pathfinder/shared";

import { THREAD_BLOCK_GAP } from "@/components/ai-elements/rhythm";
import { TaskRow, type TaskOutcome } from "@/features/conversation/thread/TaskRow";
import { humanizeToolName } from "@/features/conversation/toolNames";

import { useChatHelpers } from "../../runtime/chatHelpersContext";
import { taskResult } from "../../thread/taskExhibit";

const laneSchema = z.object({ variantId: z.string() });

/** The lane a progress payload names, or null when the task runs one sequence. */
function laneOf(progress: TaskProgress): string | null {
  return laneSchema.safeParse(progress.toolSpecific).data?.variantId ?? null;
}

export function DataBackgroundTaskStarted({ data }: { data: BackgroundTaskStarted }) {
  const chat = useChatHelpers();
  const { lanes, completed } = taskLifecycle(chat.messages, data.taskId, { laneOf });

  const tool = humanizeToolName(data.toolName);
  const result =
    completed?.status === "success" ? taskResult(chat.messages, data.taskId) : null;
  const rows = orderedLanes(lanes).map(([lane, progress], index) => (
    <TaskRow
      key={lane ?? "task"}
      label={lane === null ? tool : `${tool} - ${lane}`}
      percent={completed === null ? (progress?.percent ?? null) : 1}
      message={progress?.message ?? null}
      estimatedSeconds={lane === null ? data.estimatedDurationSeconds : null}
      outcome={outcomeOf(completed)}
      error={index === 0 ? (completed?.error ?? null) : null}
      summary={index === 0 ? (result?.summary ?? null) : null}
    />
  ));
  return (
    <div
      data-testid="data-background-task-started"
      className={`flex flex-col ${THREAD_BLOCK_GAP}`}
    >
      {completed === null ? (
        rows
      ) : (
        <div
          data-testid="data-task-completed"
          className={`flex flex-col ${THREAD_BLOCK_GAP}`}
        >
          {rows}
        </div>
      )}
    </div>
  );
}

function outcomeOf(completed: TaskCompletion | null): TaskOutcome {
  if (completed === null) return "running";
  return completed.status === "success" ? "success" : "failure";
}
